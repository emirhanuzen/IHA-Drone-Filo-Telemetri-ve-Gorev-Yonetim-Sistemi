#!/usr/bin/env bash
set -e

# API konteyneri başlarken otomatik olarak Alembic migration'larını uygular.
# Yalnızca API servisinde çalışması gerekir; worker'da migration atlanır.
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  echo "Alembic migration'ları uygulanıyor..."
  alembic upgrade head
fi

exec "$@"
