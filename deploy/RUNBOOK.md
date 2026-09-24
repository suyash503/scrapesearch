# Deploy runbook: ScrapeSearch on an Ubuntu VPS

You run every command here yourself. Each one has a one-line explanation. Replace:

- `SERVER_IP` with your VPS's public IP
- `example.com` with your domain (or skip the HTTPS steps and use the IP)
- `YOUR_GITHUB_USER` with your GitHub username

**Target:** Ubuntu 24.04 LTS, at least **2 GB RAM** (4 GB is comfortable). ES (512 MB heap), MySQL,
3 gunicorn workers and a headless Chrome during the nightly scrape all have to fit.

**Where each command runs:**
- 💻 = your laptop (PowerShell)
- 🖥️ = the server

---

## 0. Before you start (💻)

The server pulls code from GitHub, so the repo has to be pushed first. Git on Windows doesn't record the
executable bit, so set it on the scripts explicitly before you commit:

```bash
git add --chmod=+x deploy/scripts/*.sh docker/mysql-init/*.sh
```
Marks the scripts executable in git, so they're runnable after `git clone` on Linux.

Push to a **private** GitHub repo: `.env` is gitignored, but keep the repo private anyway.

---

## 1. SSH keys, a non-root user, firewall

### 1.1 SSH key (💻)

```bash
ssh-keygen -t ed25519 -C "scrapesearch-vps"
```
Creates a key pair in `~/.ssh/`: `id_ed25519` (private, never share) and `id_ed25519.pub` (public).

```bash
Get-Content ~/.ssh/id_ed25519.pub
```
Prints the public key. Paste it into your VPS provider's "SSH keys" setting when you create the server.

```bash
ssh root@SERVER_IP
```
First login, as root, with the key.

### 1.2 Update and create the `deploy` user (🖥️ as root)

```bash
apt update && apt upgrade -y
```
Installs security updates before anything else.

```bash
adduser deploy
```
Creates the user the app runs as. Set a strong password: sudo will ask for it.

```bash
usermod -aG sudo deploy
```
Lets `deploy` run admin commands through `sudo`.

```bash
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy
```
Copies root's authorized SSH key to `deploy`, so you can log in as `deploy` with the same key.

```bash
chmod 711 /home/deploy
```
Ubuntu 24.04 makes home folders `750`. nginx (user `www-data`) needs to *pass through* `/home/deploy`
to reach the React build. `711` allows passing through but not listing the contents.

**Now open a second terminal and check that `ssh deploy@SERVER_IP` works before you continue.**
The next step turns off root login. If the deploy login doesn't work, you'd lock yourself out.

### 1.3 Harden SSH (🖥️ as deploy)

```bash
sudo tee /etc/ssh/sshd_config.d/99-hardening.conf > /dev/null <<'EOF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
EOF
```
Only key-based logins, and never as root. This stops password-guessing bots completely.

```bash
sudo sshd -t && sudo systemctl reload ssh
```
`sshd -t` validates the config first. A typo there plus a reload could lock you out.

### 1.4 Firewall (🖥️)

```bash
sudo ufw default deny incoming
```
Blocks every incoming connection unless a rule below allows it.

```bash
sudo ufw default allow outgoing
```
The server can still reach the internet (apt, GitHub, the sites it scrapes).

```bash
sudo ufw allow OpenSSH
```
Opens port 22. **Do this before `ufw enable`**, or you cut off your own SSH session.

```bash
sudo ufw allow 80/tcp && sudo ufw allow 443/tcp
```
HTTP and HTTPS for nginx. Nothing else.

```bash
sudo ufw enable && sudo ufw status verbose
```
Turns the firewall on and shows the rules: 22, 80 and 443 allowed, everything else denied.

**Why MySQL (3306) and Elasticsearch (9200) must never be public:**
- Nothing outside the server needs them. Only Django and the scrapers talk to them, locally.
- Bots scan the whole IPv4 space for these ports within minutes. Open, unauthenticated ES and MySQL
  instances have been mass-wiped and held for ransom.
- ES exposes a full HTTP API. With port 9200 open, `DELETE /books` is one `curl` away for anyone.
- That's why we use defense in depth: services bind to `127.0.0.1` only, **and** the firewall blocks
  them, **and** ES has authentication.

Optional but recommended:

```bash
sudo apt install -y unattended-upgrades fail2ban
```
Automatic security updates, plus temporary bans for IPs that keep failing SSH logins.

---

## 2. Install everything

### 2.1 Swap (🖥️, only if RAM ≤ 2 GB)

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
```
Creates 2 GB of swap: disk used as overflow memory, so a memory spike slows the server down instead of
the kernel killing ES or MySQL.

```bash
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```
Keeps the swap after a reboot.

### 2.2 Base packages (🖥️)

```bash
sudo apt install -y git curl build-essential pkg-config python3-venv python3-dev default-libmysqlclient-dev nginx
```
Git, compilers and MySQL headers (needed to build `mysqlclient`), Python virtualenv support, and nginx.

### 2.3 MySQL (🖥️)

```bash
sudo apt install -y mysql-server
```
Installs MySQL 8. Ubuntu's config already binds it to `127.0.0.1` only.

```bash
sudo mysql_secure_installation
```
Interactive hardening: removes anonymous users and the test database, and disables remote root login.

```bash
sudo mysql
```
Opens a MySQL root shell (Ubuntu authenticates root through the OS user, so no password is needed). Then run:

```sql
CREATE DATABASE scrapesearch CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'scrapesearch'@'127.0.0.1' IDENTIFIED BY 'A-LONG-RANDOM-PASSWORD';
GRANT ALL PRIVILEGES ON scrapesearch.* TO 'scrapesearch'@'127.0.0.1';
EXIT;
```
Creates the app's database and a user that can only touch that one database, and only from this machine.

```bash
printf '[mysqld]\ndefault-time-zone = +00:00\n' | sudo tee /etc/mysql/mysql.conf.d/zz-scrapesearch.cnf
```
Pins MySQL to UTC, same as local, so `CURRENT_TIMESTAMP` and Django agree (this matters for `sync_es --since`).

```bash
sudo systemctl restart mysql && sudo ss -tlnp | grep 3306
```
Applies the setting. The listener must show `127.0.0.1:3306`, **not** `0.0.0.0:3306`.

### 2.4 Elasticsearch 8 (🖥️)

```bash
curl -fsSL https://artifacts.elastic.co/GPG-KEY-elasticsearch | sudo gpg --dearmor -o /usr/share/keyrings/elasticsearch-keyring.gpg
```
Adds Elastic's signing key, so apt can verify the packages really come from Elastic.

```bash
echo "deb [signed-by=/usr/share/keyrings/elasticsearch-keyring.gpg] https://artifacts.elastic.co/packages/8.x/apt stable main" | sudo tee /etc/apt/sources.list.d/elastic-8.x.list
```
Adds the 8.x apt repository. Our Python client is 8.x, and the major versions must match.

```bash
sudo apt update && sudo apt install -y elasticsearch
```
Installs ES. **The output prints a generated password for the `elastic` user: copy it now.**
(Lost it? `sudo /usr/share/elasticsearch/bin/elasticsearch-reset-password -u elastic` makes a new one.)

```bash
printf -- '-Xms512m\n-Xmx512m\n' | sudo tee /etc/elasticsearch/jvm.options.d/heap.options
```
Fixed 512 MB heap (use `1g` on a 4 GB server). Leave the other half of RAM for the OS page cache, which Lucene relies on.

```bash
sudo sed -i 's/^http.host:.*/http.host: 127.0.0.1/' /etc/elasticsearch/elasticsearch.yml
```
The package's auto-configuration makes ES listen on **all** interfaces (`0.0.0.0`). This restricts it to localhost.

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now elasticsearch
```
Starts ES now and on every boot. The first start takes about 30 seconds.

```bash
sudo ss -tlnp | grep 9200
```
Must show `127.0.0.1:9200` (or `[::1]:9200`), never `0.0.0.0` or `*`.

```bash
sudo curl --cacert /etc/elasticsearch/certs/http_ca.crt -u elastic https://localhost:9200
```
Asks for the `elastic` password and shows the cluster info. Security is on: HTTPS plus a password.

### 2.5 Node.js 22 (🖥️)

Ubuntu's own `nodejs` package is too old for Vite 8, so use NodeSource's repository:

```bash
curl -fsSL https://deb.nodesource.com/setup_22.x -o nodesource_setup.sh && less nodesource_setup.sh
```
Downloads the setup script and lets you **read it before running it**. Never pipe unknown scripts straight into sudo.

```bash
sudo bash nodesource_setup.sh && sudo apt install -y nodejs && node --version
```
Adds the repo and installs Node 22 (`v22.x`).

### 2.6 Chrome for Selenium (🖥️)

```bash
curl -fsSLO https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
```
Downloads the official Chrome package.

```bash
sudo apt install -y ./google-chrome-stable_current_amd64.deb && google-chrome --version
```
Installs it with its dependencies, and adds Google's apt repo so `apt upgrade` keeps Chrome updated.

You don't install chromedriver by hand: Selenium Manager downloads the version that matches Chrome the
first time the script runs, into `~/.cache/selenium`.

### 2.7 The app (🖥️ as deploy)

```bash
ssh-keygen -t ed25519 -C "scrapesearch-server" -f ~/.ssh/github_deploy -N ""
```
A key that is only for this server to read the repo.

```bash
cat ~/.ssh/github_deploy.pub
```
Add this on GitHub under repo → Settings → **Deploy keys** (read-only). The server can pull this
one repo and nothing else in your account.

```bash
printf 'Host github.com\n  IdentityFile ~/.ssh/github_deploy\n' >> ~/.ssh/config
```
Tells git to use that key for GitHub.

```bash
git clone git@github.com:YOUR_GITHUB_USER/scrapesearch.git ~/scrapesearch && cd ~/scrapesearch
```
Gets the code.

```bash
chmod +x deploy/scripts/*.sh
```
Just in case the executable bit didn't survive (see step 0).

```bash
sudo cp /etc/elasticsearch/certs/http_ca.crt ~/scrapesearch/http_ca.crt && sudo chown deploy: ~/scrapesearch/http_ca.crt
```
A copy of ES's CA certificate the app can read, so the Python client can verify ES's HTTPS.

```bash
cp .env.example .env && chmod 600 .env && nano .env
```
Creates the production config, readable only by `deploy`. Set:

```ini
MYSQL_PASSWORD=<the one from 2.3>
MYSQL_HOST=127.0.0.1
ES_URL=https://localhost:9200
ES_USERNAME=elastic
ES_PASSWORD=<from 2.4>
ES_CA_CERTS=/home/deploy/scrapesearch/http_ca.crt
DJANGO_SECRET_KEY=<run: python3 -c "import secrets; print(secrets.token_urlsafe(50))">
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=example.com,www.example.com,SERVER_IP
```

```bash
python3 -m venv .venv && .venv/bin/pip install -r scraper/requirements.txt -r backend/requirements.txt
```
The virtualenv plus every Python dependency (this compiles `mysqlclient` using the headers from 2.2).

```bash
.venv/bin/python backend/manage.py migrate
```
Creates the tables. Django migrations own the schema.

```bash
.venv/bin/python backend/manage.py collectstatic --noinput
```
Copies Django admin CSS/JS into `backend/staticfiles/` for nginx to serve.

```bash
(cd frontend && npm ci && npm run build)
```
Builds the React app into `frontend/dist/`.

```bash
mkdir -p logs && cd scraper && ../.venv/bin/scrapy crawl books
```
First full scrape, about 12 minutes. Its log goes to `scraper/logs/scrapy.log`.

```bash
../.venv/bin/python quotes_selenium.py --max-pages 1 && ../.venv/bin/python quotes_selenium.py
```
A 1-page smoke test (proves headless Chrome and chromedriver work on the server), then all 10 pages.

```bash
cd .. && .venv/bin/python backend/manage.py sync_es
```
First full index build into ES.

```bash
.venv/bin/python backend/manage.py check --deploy
```
Django's production checklist. The remaining HSTS warnings are explained in step 4.

---

## 3. gunicorn under systemd (🖥️)

```bash
sudo cp deploy/gunicorn.service /etc/systemd/system/gunicorn.service
```
Installs the unit file. Read it: every line is commented.

```bash
sudo systemctl daemon-reload
```
systemd re-reads unit files. Needed after **any** change to a `.service` file.

```bash
sudo systemctl enable --now gunicorn
```
`enable` = start on boot, `--now` = also start right away.

```bash
systemctl status gunicorn
```
Should show `active (running)` and 4 processes: 1 master and 3 workers.

```bash
curl -s http://127.0.0.1:8000/api/health
```
`{"status": "ok"}`: Django answers on localhost. It isn't reachable from outside, which is the point.

```bash
journalctl -u gunicorn -f
```
Live logs (Ctrl+C to exit). Every search logs a line here.

**Restart on failure**: `Restart=on-failure` brings gunicorn back 5 seconds after a crash. Try it:

```bash
sudo kill -9 "$(systemctl show -p MainPID --value gunicorn)" ; sleep 6 ; systemctl status gunicorn
```
Hard-kills the gunicorn master (systemd tracks its PID as `MainPID`). Six seconds later systemd has
restarted it: compare the new PID and the "Active: since" time.

---

## 4. nginx (🖥️)

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/scrapesearch && sudo nano /etc/nginx/sites-available/scrapesearch
```
Installs the site config. Change `server_name example.com www.example.com;` to your domain (or `_` for "any").

```bash
sudo ln -s /etc/nginx/sites-available/scrapesearch /etc/nginx/sites-enabled/ && sudo rm -f /etc/nginx/sites-enabled/default
```
Enables our site and disables the default "Welcome to nginx" page.

```bash
sudo nginx -t && sudo systemctl reload nginx
```
`nginx -t` validates the config. **Always** run it before reloading: a broken config plus a restart means downtime.

```bash
curl -sI http://SERVER_IP/ | head -5
```
(💻) `200 OK` with `Cache-Control: no-cache`: the React app.

```bash
curl -s "http://SERVER_IP/api/search?q=harry" | head -c 300
```
(💻) JSON from Django through nginx.

```bash
curl -sI -H "Accept-Encoding: gzip" http://SERVER_IP/assets/$(ls frontend/dist/assets | grep '\.js$')
```
(🖥️) Look for `Content-Encoding: gzip` and `Cache-Control: max-age=31536000`: compression and one-year
caching both work. Also check that `X-Content-Type-Options: nosniff` is there (see the `add_header` comment in nginx.conf for why that isn't automatic).

### HTTPS with certbot (needs a domain)

Create an **A record** for `example.com` (and `www`) pointing to `SERVER_IP` at your DNS provider, and wait
for `nslookup example.com` to return it.

```bash
sudo apt install -y certbot python3-certbot-nginx
```
Let's Encrypt's client plus its nginx plugin.

```bash
sudo certbot --nginx -d example.com -d www.example.com
```
Gets a free certificate, adds the `listen 443 ssl` lines to our config, and sets up the http→https redirect.

```bash
sudo certbot renew --dry-run
```
Certificates last 90 days. A systemd timer renews them automatically, and this checks that renewal will work.

Then tell Django it's behind HTTPS. Edit `.env`:

```ini
DJANGO_HTTPS=1
DJANGO_CSRF_TRUSTED_ORIGINS=https://example.com,https://www.example.com
DJANGO_HSTS_SECONDS=3600
```

```bash
sudo systemctl restart gunicorn
```
Picks up the new env values (`EnvironmentFile` is read on start).

HSTS makes browsers refuse plain HTTP for that many seconds, and **you can't take it back early**. Start
at 3600 (1 hour). Raise it to 31536000 (1 year) once you're sure HTTPS is solid. Only turn on
`SECURE_HSTS_INCLUDE_SUBDOMAINS` or preload if **every** subdomain of your domain serves HTTPS, which is
why `check --deploy` still warns about them.

---

## 5. Cron: nightly scrape + sync (🖥️ as deploy)

```bash
crontab deploy/scraper.cron && crontab -l
```
Installs the schedule for `deploy` (this replaces the existing crontab) and prints it back.

```bash
timedatectl
```
Cron uses the server's time zone, usually UTC on a VPS. 02:30 UTC = 08:00 IST.

Test the nightly job **now** instead of waiting until 02:30. Paste the command part of the `30 2 * * *` line:

```bash
APP=~/scrapesearch PY=~/scrapesearch/.venv/bin LOGS=~/scrapesearch/logs flock -n /tmp/scrapesearch-nightly.lock bash -c 'cd $APP/scraper && $PY/scrapy crawl books && $PY/python quotes_selenium.py && $PY/python $APP/backend/manage.py sync_es --since 26h' >> ~/scrapesearch/logs/nightly.log 2>&1 &
```
Runs the exact nightly pipeline in the background.

```bash
tail -f ~/scrapesearch/logs/nightly.log ~/scrapesearch/scraper/logs/scrapy.log
```
Watch it: Scrapy's progress, then the quotes, then `incremental: N books re-indexed`. Nothing changed
since the first scrape, so expect `mysql/books_unchanged: 1000` and `0 books re-indexed`.

**Why cron jobs break when "it works in my terminal":** cron starts with an almost empty environment
(no `PATH` from your shell, no activated venv, a different working directory). That's why the crontab
uses absolute paths everywhere and the Python code loads `.env` itself.

---

## 6. The bash scripts

Each one has `set -euo pipefail`, a usage message (`-h`), and comments on the non-obvious lines.

| Script | Run it | What it does |
|---|---|---|
| `deploy.sh` | `deploy/scripts/deploy.sh` | git pull (fast-forward only) → pip install → migrate → collectstatic → `npm ci && build` → `systemctl reload-or-restart gunicorn` → health check with retries. Stops at the first failure. |
| `backup_mysql.sh` | `deploy/scripts/backup_mysql.sh` | `mysqldump --single-transaction` → gzip → verify → atomic rename; deletes dumps older than 7 days. Cron runs it at 03:15. |
| `check_logs.sh` | `deploy/scripts/check_logs.sh 24` | Counts ERROR, CRITICAL and Traceback lines from the last N hours in journald (gunicorn) and every log file, and shows the latest ones. Exits 1 if any are found. |
| `healthcheck.sh` | `deploy/scripts/healthcheck.sh` | API `/api/health`, ES cluster status (not red), and `books` has documents. Exits 1 on any failure. Cron runs it every 5 minutes with `--quiet`, so the log only has failures. |

`deploy.sh` needs `sudo` for one command. To run it unattended (for example from CI), allow only that command:

```bash
echo 'deploy ALL=(root) NOPASSWD: /usr/bin/systemctl reload-or-restart gunicorn' | sudo tee /etc/sudoers.d/deploy-gunicorn && sudo chmod 440 /etc/sudoers.d/deploy-gunicorn && sudo visudo -c
```
Passwordless sudo for exactly that one command, nothing else. `visudo -c` validates it, because a broken sudoers file can lock you out of sudo.

**Bash details worth knowing in an interview:**
- `set -e` exits on the first failing command, `-u` treats unset variables as errors, and `-o pipefail`
  makes `mysqldump | gzip` fail when `mysqldump` fails (by default a pipeline only reports the *last* command's status).
- `grep` exits 1 when it finds nothing, so under `set -e` "no errors found" would kill the script. Hence `|| true`.
- `((count++))` returns "false" when count is 0, which also kills a `set -e` script. Use `count=$((count + 1))`.
- `trap '...' EXIT` runs cleanup whether the script succeeds or fails, like deleting the temporary MySQL password file.
- Passwords never go on the command line (`-pSECRET`): every user can see them with `ps aux`.
- The scripts read `.env` line by line instead of `source .env`, because `source` would *execute* the file.

---

## 7. Debugging drill: break it, then diagnose it

Do these one at a time, on purpose, and fix each one before starting the next.

### Toolbox

| Command | Answers the question |
|---|---|
| `systemctl status X` | Is service X running? Since when? What were its last log lines? |
| `journalctl -u X -n 50 --no-pager` | What did service X log recently? Add `-f` to follow, `--since "10 min ago"` to narrow it down. |
| `df -h` | Is a disk full? |
| `du -xh / --max-depth=2 2>/dev/null \| sort -h \| tail` | *What* is filling the disk? |
| `free -m` | How much RAM and swap is used? (Look at the "available" column, not "free".) |
| `sudo lsof -i :9200` / `sudo ss -tlnp` | Who is listening on a port, and on which address? |
| `tail -f FILE` | Watch a log file live. |
| `namei -l /some/path` | Permissions of every directory along a path (great for "Permission denied"). |
| `journalctl -k \| grep -i "killed process"` | Did the kernel kill something because RAM ran out (the OOM killer)? |

### Drill A: Elasticsearch stops

```bash
sudo systemctl stop elasticsearch
```
Simulates ES crashing.

**Symptom:** the site loads, but searches show "Search is temporarily unavailable" (the API returns 503).
We built it to degrade gracefully instead of throwing a 500.

```bash
deploy/scripts/healthcheck.sh
```
`OK api`, `FAIL elasticsearch: curl: (7) Failed to connect`: the API is fine, ES is the problem.

```bash
systemctl status elasticsearch
```
`inactive (dead)`, plus the time it stopped.

```bash
sudo lsof -i :9200
```
Returns nothing: no process is listening on 9200.

```bash
journalctl -u gunicorn --since "5 min ago" | grep -i elasticsearch
```
Django logged `Elasticsearch request failed` for each failed search. This is how you'd find it from the app side.

```bash
sudo systemctl start elasticsearch && sleep 30 && deploy/scripts/healthcheck.sh
```
Fixes it. All OK again, with no Django restart needed: the client reconnects on its own.

If ES dies **by itself**, check memory with `free -m` and `journalctl -k | grep -i oom`. On a small
server the usual culprit is the kernel's OOM killer choosing the biggest process (ES).

### Drill B: the disk fills up

```bash
df -h /
```
Note "Avail" and "Use%" first.

```bash
sudo fallocate -l $(( $(df --output=avail -B1 / | tail -1) - $(df --output=size -B1 / | tail -1) * 3 / 100 )) /var/tmp/fill.img
```
Creates one big file that leaves only ~3% free, past ES's 95% "flood stage" watermark but not quite 100%
(a completely full disk can also break SSH logins and journald).

```bash
df -h /
```
Now `Use%` is about 97%.

```bash
.venv/bin/python backend/manage.py sync_es
```
Fails with `cluster_block_exception ... index read-only / allow delete (api)`. At 95% disk usage ES
protects itself by making every index read-only. Searches still work, but writes don't.

```bash
sudo du -xh / --max-depth=2 2>/dev/null | sort -h | tail
```
Finds the space hog: `/var/tmp` is suddenly huge. On a real server it's usually `/var/log`, old backups, or `journalctl --disk-usage`.

```bash
sudo rm /var/tmp/fill.img && df -h /
```
Frees the space. ES 8 lifts the read-only block automatically once usage drops below the high watermark (90%).

```bash
.venv/bin/python backend/manage.py sync_es
```
Works again.

Prevention: `backup_mysql.sh` already keeps only 7 days. Also cap journald with
`SystemMaxUse=500M` in `/etc/systemd/journald.conf`, and watch `df -h` in your health checks.

### Drill C: wrong permissions

```bash
sudo chmod 700 /home/deploy
```
Simulates a common mistake: the home folder locked down so nginx (`www-data`) can't get into it.

```bash
curl -sI http://localhost/ | head -1
```
`403 Forbidden` or `500`: nginx can't read the React build. (The API still works, because it goes to gunicorn over TCP.)

```bash
sudo tail -n 5 /var/log/nginx/error.log
```
`open() "/home/deploy/scrapesearch/frontend/dist/index.html" failed (13: Permission denied)`. The log tells you exactly what's wrong.

```bash
sudo -u www-data namei -l /home/deploy/scrapesearch/frontend/dist/index.html
```
Walks the path as nginx's user and shows each directory's permissions. `/home/deploy` shows `drwx------`, which is the blocker.

```bash
sudo chmod 711 /home/deploy && curl -sI http://localhost/ | head -1
```
Fixed: `200 OK`.

A second one, for systemd:

```bash
chmod 000 ~/scrapesearch/.env && sudo systemctl restart gunicorn
```
gunicorn can't read its secrets.

```bash
systemctl status gunicorn
```
`Failed to load environment files: Permission denied` → `failed`. systemd refuses to start the service at all.

```bash
chmod 600 ~/scrapesearch/.env && sudo systemctl restart gunicorn && systemctl status gunicorn
```
Fixed.

### Drill D: something is already using the port

```bash
sudo systemctl stop gunicorn && python3 -m http.server 8000 --bind 127.0.0.1 &
```
Something else grabs port 8000 while gunicorn is down.

```bash
sudo systemctl start gunicorn ; journalctl -u gunicorn -n 5 --no-pager
```
`Connection in use: ('127.0.0.1', 8000)`: gunicorn can't bind to the port.

```bash
sudo lsof -i :8000
```
Shows the `python3` process (and its PID) holding the port.

```bash
kill %1 && sudo systemctl start gunicorn && systemctl status gunicorn
```
Stops the squatter, and gunicorn starts.

### The 60-second triage when "the site is down"

1. `deploy/scripts/healthcheck.sh`: which layer is broken?
2. `systemctl status nginx gunicorn elasticsearch mysql`: what's not running?
3. `journalctl -u <the broken one> -n 50`: why?
4. `df -h` and `free -m`: out of disk or memory?
5. `sudo tail -n 20 /var/log/nginx/error.log`: is nginx failing to reach gunicorn or the files?
6. `deploy/scripts/check_logs.sh 2`: any errors in the last 2 hours?
