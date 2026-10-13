# 为什么做 buildthaw

调研日期：2026-10-13（UTC）。有效窗口为 **2026-07-13 至 2026-10-13**，按原帖创建日期计数。只读取官方公开项目的讨论、文档和官方包注册表；未登录，未进行任何 GitHub 写操作。外部内容只用于事实核查。

## 最多三个候选

| 候选 | 近期证据与现有方案 | 决定 |
| --- | --- | --- |
| Python 本地模块遮蔽标准库 | 搜索 CPython、uv、Ruff、pytest、Pydantic 的近期官方 issues，未核实到三位独立用户对同一可由本地扫描解决的问题的直接报告；不少结果其实是分析器或 lazy import 的缺陷。Ruff 当前 0.17.0 已有 `stdlib-module-shadowing`（A005）规则。 | 淘汰，不把相邻问题算作证据。 |
| TypeScript 增量缓存留下过期诊断或漏报错误 | 下述三位独立报告者均在有效窗口内，明确比较了增量检查和清除缓存后的结果。官方编译器有强制重建与整体清理，但缺少这里需要的“只清缓存、保留产物、检查文件再删除”的独立操作。 | **入选，只实施这一项。** |
| `.env` 变量重复与覆盖排查 | Vite #23460 报告加载优先级不清楚；Compose #13945 涉及 include 的覆盖行为。其余结果多为解密、hook 环境或插值缺陷，未凑成三位用户对同一问题的证据。dotenvx 当前 2.34.2 已提供变量获取功能，跨框架精确还原语义会扩大范围。 | 淘汰；不把不同根因拼成三条。 |

搜索使用 `is:issue created:2026-07-13..2026-10-13`，分别限制上述官方仓库并查询 `shadowing`、`tsbuildinfo`、`.env variable`。没有比较第四个候选。未选择或扩展 shebanglf、ignoretrail、treeport、lockgrain、prgate；本工具不处理换行、忽略规则、Git 文件名、锁文件或 PR。

候选核查链接：[Ruff 0.17.0](https://github.com/astral-sh/ruff/releases/tag/0.17.0)、[Ruff A005 文档](https://docs.astral.sh/ruff/rules/stdlib-module-shadowing/)、[Vite #23460，2026-09-09](https://github.com/vitejs/vite/issues/23460)、[Compose #13945，2026-07-16](https://github.com/docker/compose/issues/13945)、[dotenvx 当前版本元数据](https://registry.npmjs.org/@dotenvx/dotenvx/latest)。

## 入选的三条独立公开原话

均为 Microsoft/TypeScript 官方 issue 原作者的原文，没有使用转载、同人重复或旧帖。该仓库调研时有 111,429 stars。日期来自公开 GitHub API 的 `created_at`，原文同时保存于 `research/evidence.json`。三帖核查时均 open；这不代表所有 TypeScript 版本都会触发这些缺陷。

1. **infomiho，2026-09-22 11:39:55 UTC** — [TypeScript #64386](https://github.com/microsoft/TypeScript/issues/64386)

   > Step 4 succeeds. Incremental and clean builds disagree on identical source files.

   第 4 步是删除 `.cache/tsconfig.tsbuildinfo` 再执行检查。报告复现版本为 6.0.3、7.0.2、7.1.0-dev.20260922.1。问题是修改 module augmentation 后仍显示已经过期的 TS2322。

2. **valeralebedz，2026-09-30 13:29:14 UTC** — [TypeScript #64552](https://github.com/microsoft/TypeScript/issues/64552)

   > In both shapes the wrong result persists on later runs with no further change. It clears only when the .tsbuildinfo is deleted.

   修改 `lib` / `target` 后出现残留报错或漏报。报告 7.0.2 以及特定 nightly 仍有问题；同时说明 5.9.3 和 6.0.3 在该复现上正常。这是缓存失效问题，不能推广成所有版本皆有错。

3. **plum117，2026-10-10 01:58:09 UTC** — [TypeScript #64715](https://github.com/microsoft/TypeScript/issues/64715)

   > The incremental build and the clean build disagree on the same files.

   > Found in the type tests of [expect-webdriverio](https://github.com/webdriverio/expect-webdriverio): its global `expect` and the `ExpectWebdriverIO` namespace come from a `declare global` block in a module declaration file of the package. Vitest runs its type tests with `tsc --noEmit --incremental --tsBuildInfoFile <vitest>/dist/tsconfig.tmp.tsbuildinfo`, so a broken public type gave 141 passed tests, while a clean `tsc` found 22 errors. Workaround: delete the build info file before each run (webdriverio/expect-webdriverio#2357).

   报告对比 7.0.2 与 6.0.3，并明确指出删除缓存是临时解决方法。依赖目录中的这种缓存需要本工具的显式 `--cache` 参数，默认扫描不进入 `node_modules`。

三位用户分别报告了相同可干预点：**保留的 TypeScript build info 导致重新检查仍不可信，移除对应缓存可触发冷检查**。本工具只完成这个清除步骤；不会证明代码正确，也不会修复编译器的失效算法。超过三个月的帖子未纳入门槛，也不需要用旧帖补数。

## 现有工具和当前版本核查

版本均核查于 2026-10-13，不把帖子里的版本当成当前版本。

| 工具 | 已核查版本 / 来源 | 已能解决什么，仍有什么成本 |
| --- | --- | --- |
| TypeScript `tsc` | npm `latest` 为 **7.0.2**；[官方元数据](https://registry.npmjs.org/typescript/latest)、[项目引用文档](https://www.typescriptlang.org/docs/handbook/project-references.html) | `tsc -b --force` 将项目视为过期并立即重建，是已有可用替代。`tsc -b --clean` 删除指定项目的输出，范围包括 `.js` / `.d.ts`，并非只清缓存。若愿意重建，直接用官方命令即可。 |
| `rm` / `find` / PowerShell | OS 内置，语法与版本依宿主而定；本工具不依赖它们 | 已知一个缓存路径时，手工删除通常更简单。递归删除需要自己排除依赖、版本控制目录、软链接，并避免把名称相似的非缓存文件删掉。 |
| rimraf | npm `latest` 为 **6.1.3**；[官方元数据](https://registry.npmjs.org/rimraf/latest)、[官方 README](https://github.com/isaacs/rimraf#readme) | 已提供跨平台删除和 glob；不验证 TypeScript 缓存结构，也不决定哪些目录该跳过。用户仍需维护 glob / 排除规则。 |

官方 [`tsBuildInfoFile` 文档](https://www.typescriptlang.org/tsconfig/tsBuildInfoFile.html) 说明缓存位置受 `outFile`、`rootDir`、`outDir`、配置名和显式配置影响。因此本工具发现实际存在的缓存文件，不重新实现 tsconfig 继承和路径计算。自定义后缀、被排除目录中的缓存用显式路径选择。

rimraf 的固定版本 raw README 请求超时后，改为读取官方 npm 上 6.1.3 发布包内的 README，并校验发布包 integrity；其中明确写着 “Globbing requires the `--glob` CLI option or `glob` option property”。记录见 `research/rimraf-doc-check.json`，没有把网络超时冒充成功核查。

## 最终范围和取舍

**buildthaw** 是 Python 标准库 CLI。默认预览项目内的 `.tsbuildinfo`；`--apply` 在预检通过后只删除被识别的缓存，保留源码和编译产物。支持多个显式 `--cache` 路径；所有目标必须在给定根目录内。默认跳过依赖、版本控制和虚拟环境目录；不跟随软链接。

这不是发明新的 TypeScript 缓存修复算法。原创工作在于把这个反复出现的维护操作做成小而可检查的离线工具：候选发现、结构识别、删除前完整预检、可读清单和明确退出码。价值有限但具体：大型仓库多处缓存、不同 shell 或不希望动产物时能省掉手写清理脚本。

不登录、不请求第三方 API、不编译或执行项目代码、不读环境变量或凭据、不修改配置。用户正常安装后单命令 `buildthaw . --apply` 完成缓存清理；重新运行原有 typecheck / build 命令由用户负责。无法自动判断某份缓存是否真的过期；清理后可能增加下一次构建耗时。写入中的缓存不适合清理，应先停止 watch/build。

范围进一步限定为 POSIX 系统上的静止、可信目录；没有事务、撤销或并发替换防护。只支持现代扁平和简化 build-mode JSON，不支持旧 `program` 嵌套格式。未知/损坏/超过 64 MiB/超过 64 层嵌套的缓存会被拒绝，不以扩展删除权限的方式绕过检查。没有安装器时也可以单命令 `python3 buildthaw.py /path/to/project --apply` 运行。

## 验证方法

测试只通过 CLI 公开边界观察退出码、输出和文件变化，使用项目内临时目录与合成文件。严格逐条测试失败后再最小实现，过程见 `tdd-log.md`。另用从官方 npm 下载、校验 integrity 的 TypeScript 7.0.2 编译器生成真实缓存，核验清理后编译产物保持不变、下一次构建能够重新生成缓存。

实际结果：incremental、composite、普通 build 三种模式的往返验证均通过。并在 Linux 本机复现 #64386：源码修正后仍 exit 1 / TS2322，清缓存后同一源码 exit 0；详见 `research/reproduction.json`。还实际执行了当前编译器的 `--clean --dry`，它列出 `.js` 和 `.tsbuildinfo` 两种待删除文件。因此这里只声称验证了这一个具体缺陷复现，不把其余两帖的用户报告冒充本机测试。
