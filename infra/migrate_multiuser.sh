#!/usr/bin/env bash
# Migración única (01-11-2026) a la versión multipersona: copia los datos del dueño a su carpeta
#   state/*        -> users/<uid>/state/*
#   site/data.js   -> site/u/<uid>/data.js     site/acts/* -> site/u/<uid>/acts/*
#   SSM /garmin-stats/garmin-key -> /garmin-stats/users/<uid>/garmin-key
# y crea el registro admin/users.json con el dueño. Solo copia: lo antiguo se borra aparte tras comprobarlo.
set -euo pipefail
export AWS_PROFILE=${AWS_PROFILE:-default} AWS_REGION=${AWS_REGION:-eu-west-1} AWS_PAGER=""
B=garmin-stats-site-123456789012
OWNER=tu@gmail.com
UID_=$(python3 -c "
import json,hmac,hashlib
s=json.load(open('$HOME/.config/garmin/aws-secrets.json'))['session'].encode()
print(hmac.new(s, b'uid:$OWNER', hashlib.sha256).hexdigest()[:16])")
echo "uid del dueño: $UID_"
aws s3 sync "s3://$B/state/" "s3://$B/users/$UID_/state/" --only-show-errors
aws s3 cp "s3://$B/site/data.js" "s3://$B/site/u/$UID_/data.js" --only-show-errors \
  --content-type "text/javascript; charset=utf-8" --cache-control no-store --metadata-directive REPLACE
aws s3 sync "s3://$B/site/acts/" "s3://$B/site/u/$UID_/acts/" --only-show-errors \
  --content-type "text/javascript; charset=utf-8" --cache-control no-store --metadata-directive REPLACE
KEY=$(aws ssm get-parameter --name /garmin-stats/garmin-key --with-decryption --query Parameter.Value --output text)
aws ssm put-parameter --name "/garmin-stats/users/$UID_/garmin-key" --type SecureString --overwrite --value "$KEY" >/dev/null
unset KEY
TMP=$(mktemp)
python3 - "$UID_" "$OWNER" > "$TMP" <<'PY'
import json, sys, time
uid, email = sys.argv[1], sys.argv[2]
now = int(time.time())
print(json.dumps({"users": [{"email": email, "uid": uid, "name": "Sergi", "role": "owner", "budgetUsd": 50,
                             "status": "active", "invitedAt": now, "joinedAt": now, "consentAt": now, "keyAt": now}]}, indent=1))
PY
if aws s3api head-object --bucket "$B" --key admin/users.json >/dev/null 2>&1; then
  echo "admin/users.json ya existe: no lo toco"
else
  aws s3 cp "$TMP" "s3://$B/admin/users.json" --content-type application/json --only-show-errors
fi
rm -f "$TMP"
echo "copiado:"; aws s3 ls "s3://$B/users/$UID_/state/" | wc -l; aws s3 ls "s3://$B/site/u/$UID_/acts/" | wc -l
