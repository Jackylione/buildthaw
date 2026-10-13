# buildthaw 中文讲解

**一句话用途：当 TypeScript 增量检查被旧缓存卡住时，用一条本地命令清掉构建缓存，保留源码和编译产物。**

## 安装和最小用法

只需 Python 3.10+，运行时没有第三方依赖。保留本项目，或者单独复制 `buildthaw.py`，即可执行：

```sh
python3 buildthaw.py /你的/项目目录 --apply
```

这是直接运行方式，不需要 pip、Node、账号或网络。若已有 pip，也可以从当前源码目录安装命令：

```sh
python3 -m pip install --no-deps .
buildthaw /你的/项目目录 --apply
```

pip 构建阶段可能需要取得 setuptools；希望完全离线时直接运行单文件即可。此项目尚未发布到任何包注册表。

去掉 `--apply` 就是预览，列出待清理文件，不修改任何文件：

```sh
python3 buildthaw.py /你的/项目目录
```

例如输出 `CACHE ".cache/tsconfig.tsbuildinfo" (TypeScript 7.0.2)`。确认范围后运行带 `--apply` 的命令，再运行你原有的 typecheck/build。工具负责清缓存，不会自动编译，不会修改 tsconfig。

## 它解决了什么

TypeScript 会将增量构建信息写入 `.tsbuildinfo`，以便跳过重复工作。如果缓存失效逻辑出现缺陷，源码已经改对，检查仍可能报旧错误；反过来，新增错误也可能被漏掉。

选题来自三位不同用户在 2026-09-22、09-30、10-10 发布的原始报告，链接、原话和当前版本核查都在 [problem.md](problem.md)。本机还实际复现了其中的 #64386：修改类型后仍报 TS2322，清掉缓存后检查通过。工具不声称修复这些编译器缺陷，只把报告者反复执行的临时维护操作做得可检查、可重复。

`tsc -b --force` 已能强制重建；愿意直接重建时可以优先用它。`tsc -b --clean` 会连编译产物一起删除。如果只知道一个缓存路径，手工删除也更简单。buildthaw 的使用场景是：仓库里有多份缓存，希望统一清理，并保留 `.js`、`.d.ts`、source map 等文件。

## 清理范围

默认递归寻找根目录内以 `.tsbuildinfo` 结尾的普通文件，包括隐藏的 `.cache` 目录。跳过 `node_modules`、`.git`、`.hg`、`.svn`、`.venv`、`venv`、`__pycache__`，不解析 `.gitignore`，不跟随根目录内的软链接。

依赖内部缓存或自定义文件名可以显式指定：

```sh
python3 buildthaw.py /你的/项目目录 --apply \
  --cache node_modules/vitest/dist/tsconfig.tmp.tsbuildinfo \
  --cache ".cache/custom build state"
```

出现 `--cache` 后，只处理列出的文件，不再自动扫描。可重复传入；相对路径以给定根目录为准，绝对路径也必须在根目录内。拒绝 `..` 和路径中的软链接。没有提供根目录时使用当前目录。

## 遇到失败时

工具先读取并检查所有候选，预检通过后才开始删除。格式损坏、未知结构、无法读取、目录或管道等非普通文件，都会让预检以退出码 `2` 结束，不删除任何候选。重复 JSON 键、非标准数字常量、超过 64 层的 JSON、超过 64 MiB 的文件也会被拒绝。

删除过程不是事务：如果删除到一半遇到权限问题，已删除的缓存不会恢复。输出会逐条列出成功项，错误会说明已经删除多少份。退出码 `0` 表示预览完成或清理完成；找不到缓存也是成功的空操作。

## 限制

- 无法判断某份缓存是否真的过期；选择范围内、结构可识别的缓存都会被清理。下一次检查可能更慢。
- 清理前停止 watch/build，并在可信且静止的项目目录使用。没有目录锁，也不保证抵御其他进程并发替换路径或文件。
- 不读取 tsconfig，因此不会追踪跨根目录的项目引用；范围以指定的根目录为准。自定义后缀与排除目录里的文件必须显式指定。
- 只识别现代扁平 build-info 和普通 build-mode 的简化 JSON。旧的 `program` 嵌套格式及未来未知格式会被拒绝。结构检查不能证明文件一定来自 TypeScript；没有强制删除未知文件的选项。
- 没有撤销功能，正常编译会重新生成缓存。损坏缓存需要人工调查或删除。
- 已在 Linux、Python 3.14.4、TypeScript 7.0.2 下验证。本版面向 POSIX 系统，不支持 Windows junction/reparse point。

## 开发验证

在源码根目录运行：

```sh
python3 -m unittest discover -s tests -v
```

测试从命令行边界验证退出码、输出及文件变化，不测试私有实现。所有临时文件都写在本项目的 `.test-tmp/` 内；权限用例要求 POSIX 非 root 用户。可选的真实编译器用例需要 `.tools/typescript-native/package/lib/tsc`，缺失时会明确标记 skipped，不下载依赖。交付时该依赖已从官方 npm 获取并校验，实际运行了该用例。

逐条先红后绿的记录见 [tdd-log.md](tdd-log.md)。真实编译器验证覆盖 incremental、composite、普通 build 三种模式，并检查清理前后产物的字节和时间戳不变。

自评：它值得作为用途明确的小脚本公开，但不是大而全的 TypeScript 管理工具。是否发布由林峰决定；本任务没有建仓库、推送或进行任何 GitHub 写操作。
