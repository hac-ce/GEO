# 数据库迁移记录

## 0001：登记当前结构

2026-11-15，开始由 Alembic 管理学习版数据库。

- 迁移脚本：versions/0001_initial_schema.py。
- upgrade 按依赖顺序创建 brand、prompts、observations 三张表。
- downgrade 按相反顺序删除这三张表，会删除其中的数据。
- 初始脚本在临时空库上生成，未修改应用的数据库地址。
- 原数据库结构与 ORM 模型比较无差异后，使用 stamp 0001 登记版本；没有对原库执行初始建表或删表。

stamp 只登记版本，不执行脚本，也不会替你验证表结构；必须先确认实际结构匹配。
upgrade 才会执行尚未应用的升级脚本。两者不能随意互换。

## 验证结果

在独立临时库验证了从空库升级、重复升级、退回起点、重新升级。
退回操作仅针对临时库，不曾对现有业务库执行。

原库登记版本前后，三张业务表的结构及全部记录一致：
3 个品牌、1 个问题、1 条回答。SQLite 完整性检查通过。
回答表目前尚未新增 mentioned、prompted 字段。

备份为根目录的 geo_learning.before_baseline_20261115_211531_684f8a.db。
本次本地核对记录保存在 .data/baseline_audit.json。

## 后续操作

在项目根目录执行命令：

~~~powershell
# 查看数据库登记的版本。
.\.venv\Scripts\python.exe -m alembic current

# 后续修改模型后，生成候选迁移，需人工检查后才能应用。
.\.venv\Scripts\python.exe -m alembic revision --autogenerate -m "describe change"

# 执行尚未应用的升级脚本。
.\.venv\Scripts\python.exe -m alembic upgrade head
~~~

新空数据库使用 upgrade head 建表；已经登记版本的数据库只执行后续升级。
`backend/scripts/init_db.py` 的 `create_all` 保留作学习参考，后续表结构变更由 Alembic 管理。

## 0004：任务输入快照（2026-11-21）

在用户已完成的 0003 jobs 表基础上，新增 question_snapshot、brand_name_snapshot、brand_aliases_snapshot 三个可空字段。旧任务不自动回填；新任务由 create_job 显式写入提交时的问题、品牌名和别名。

迁移前使用 SQLite backup API 创建 geo_learning.before_snapshots_20261121_010904_036894.db。临时库验证升级、旧格式任务兼容、退回和重新升级、空库升级通过；原库已执行 upgrade head，版本为 0004，结构与模型一致，完整性检查通过，原有业务记录核对未变。原库未执行退回。后续业务接口应使用与 0004 匹配的模型代码。
