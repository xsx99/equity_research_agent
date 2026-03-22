## 存储
Postgres 数据目录必须放在真实磁盘路径上，而不是内存。禁止使用 /tmp、/run、/dev/shm、tmpfs、容器匿名 volume 或任何重启会丢失的数据目录。优先方案是把 Postgres 数据目录放在外接 SSD 或明确挂载的磁盘目录，例如 /data/postgres_data/。

应用日志、SQLite 缓存、下载的数据文件也都放在磁盘目录下，例如 /data/research-app/.

coding agent 在实现时，必须显式检查 Postgres data directory 配置，确保数据库文件实际落在硬盘上。需要在部署文档里写清楚如何验证这一点，例如检查 SHOW data_directory; 的输出，并确认该目录不是 tmpfs。

## 部署和CICD
所有服务，部署和CICD都复用现有基础设施。
部署方式复用Docker Compose。显式写死 volume 到硬盘路径，例如 /mnt/data/postgres:/var/lib/postgresql/data，不能用匿名卷。

## 代码要求
保持代码简单清晰
每次写完major refactor，把整体的改动加进`/documents/repo_overview.md`


## Environment setup
run `source ~/.venv/bin/activate` before using Python