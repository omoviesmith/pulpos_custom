## Pulpos Custom

Pulpos-style ERP customizations (theme, UX, validations)

#### License

MIT

### Deployment (GitHub Actions → Contabo)

- Workflow `.github/workflows/deploy.yml` triggers on pushes to `main` and `develop`, SSHes into Contabo, updates the app, and runs `bench build`, `bench migrate`, `bench clear-cache`, and `bench restart`.
- Required GitHub secrets: `CONTABO_HOST`, `CONTABO_USER`, `CONTABO_SSH_KEY` (or `CONTABO_PASSWORD`), `CONTABO_PORT` (optional, defaults to 22 if your SSH server does), `BENCH_PATH` (e.g. `/opt/bench/frappe-bench`), `SITE_NAME` (e.g. your ERPNext site), `GH_PAT` (only if the repo is private).
- The deploy uses the pushed branch name (`main`/`develop`) to `git fetch/reset` the app at `$BENCH_PATH/apps/pulpos_custom`; if the app folder is missing it will clone it.
- Bench must be available on PATH for the SSH user. If your bench runs under a different Linux user, set `CONTABO_USER` to that user or adjust the workflow to sudo to it.

### Website Items helper

- Create Website Items for Items that have a price/image:  
  `bench --site <site> execute "pulpos_custom.website_sync.create_website_items"`  
  Options (optional): `price_list="FerreTlap Retail"` (default), `default_warehouse="<Warehouse>"`, `publish=1`.
