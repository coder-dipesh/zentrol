#!/bin/bash
set -e

DB_HOST="${MOODLE_DB_HOST:-moodle-db}"
DB_USER="${MOODLE_DB_USER:-moodle}"
DB_PASS="${MOODLE_DB_PASS:-moodlepass}"
DB_NAME="${MOODLE_DB_NAME:-moodle}"
WWWROOT="${MOODLE_WWWROOT:-http://localhost:8080}"
ADMIN_USER="${MOODLE_ADMIN:-admin}"
ADMIN_PASS="${MOODLE_ADMIN_PASSWORD:-Admin1234!}"
ADMIN_EMAIL="${MOODLE_ADMIN_EMAIL:-admin@local.test}"
CONFIG=/var/www/html/config.php

# ── Wait for DB ───────────────────────────────────────────────────────────────
echo "⏳ Waiting for database at $DB_HOST..."
until php -r "
\$c = @mysqli_connect('$DB_HOST', '$DB_USER', '$DB_PASS', '$DB_NAME');
if (\$c) { mysqli_close(\$c); exit(0); } exit(1);
" 2>/dev/null; do
    echo "   still waiting..."
    sleep 3
done
echo "✅ Database is ready."

# ── Check if Moodle tables already exist ──────────────────────────────────────
INSTALLED=$(php -r "
\$c = mysqli_connect('$DB_HOST', '$DB_USER', '$DB_PASS', '$DB_NAME');
\$r = mysqli_query(\$c, \"SHOW TABLES LIKE 'mdl_config'\");
echo mysqli_num_rows(\$r);
mysqli_close(\$c);
" 2>/dev/null)

if [ "$INSTALLED" = "0" ]; then
    # ── First boot: run Moodle CLI installer ──────────────────────────────────
    echo "🚀 Installing Moodle (first boot — ~2 minutes)..."
    rm -f "$CONFIG"   # ensure installer can create it fresh
    php /var/www/html/admin/cli/install.php \
        --wwwroot="$WWWROOT" \
        --dataroot=/var/www/moodledata \
        --dbtype=mariadb \
        --dbhost="$DB_HOST" \
        --dbname="$DB_NAME" \
        --dbuser="$DB_USER" \
        --dbpass="$DB_PASS" \
        --fullname="Zentrol Test Moodle" \
        --shortname="zentrol" \
        --adminuser="$ADMIN_USER" \
        --adminpass="$ADMIN_PASS" \
        --adminemail="$ADMIN_EMAIL" \
        --non-interactive \
        --agree-license
    chown www-data:www-data /var/www/html/config.php
    chmod 644 /var/www/html/config.php
    echo "✅ Moodle installed! Admin: $ADMIN_USER / $ADMIN_PASS"
else
    # ── Subsequent boots: regenerate config.php (not persisted across restarts) ─
    echo "✅ Moodle already installed — regenerating config.php..."
    cat > "$CONFIG" << PHPEOF
<?php
unset(\$CFG);
global \$CFG;
\$CFG = new stdClass();
\$CFG->dbtype    = 'mariadb';
\$CFG->dblibrary = 'native';
\$CFG->dbhost    = '$DB_HOST';
\$CFG->dbname    = '$DB_NAME';
\$CFG->dbuser    = '$DB_USER';
\$CFG->dbpass    = '$DB_PASS';
\$CFG->prefix    = 'mdl_';
\$CFG->dboptions = ['dbpersist' => 0, 'dbport' => '', 'dbsocket' => '', 'dbcollation' => 'utf8mb4_unicode_ci'];
\$CFG->wwwroot   = '$WWWROOT';
\$CFG->dataroot  = '/var/www/moodledata';
\$CFG->admin     = 'admin';
\$CFG->directorypermissions = 0777;
require_once(__DIR__ . '/lib/setup.php');
PHPEOF
    chown www-data:www-data "$CONFIG"
fi

# ── Start Apache ──────────────────────────────────────────────────────────────
echo "🌐 Starting Apache at $WWWROOT ..."
exec apache2-foreground
