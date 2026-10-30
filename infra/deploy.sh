#!/usr/bin/env bash
# Despliega la web privada en AWS (cuenta personal, perfil `default`) con un único stack.
# Uso: infra/deploy.sh            (idempotente: se puede relanzar para actualizar)
# Todo corre en AWS: la Lambda de sincronización (cada hora) descarga de Garmin y publica la web.
set -euo pipefail
cd "$(dirname "$0")/.."
export AWS_PROFILE=${AWS_PROFILE:-default} AWS_REGION=${AWS_REGION:-eu-west-1} AWS_PAGER=""
STACK=garmin-stats
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
[ "$ACCOUNT" = "123456789012" ] || { echo "Cuenta inesperada ($ACCOUNT): solo la personal." >&2; exit 1; }
ARTIFACTS="garmin-stats-artifacts-$ACCOUNT"
SECRETS=~/.config/garmin/aws-secrets.json
EMAIL=tu@gmail.com

# 1) Secretos propios (se crean una vez y se reutilizan)
if [ ! -f "$SECRETS" ]; then
  umask 077
  python3 -c "import json,secrets; print(json.dumps({'session': secrets.token_hex(32), 'origin': secrets.token_hex(32)}))" > "$SECRETS"
fi
SESSION=$(python3 -c "import json; print(json.load(open('$SECRETS'))['session'])")
ORIGIN=$(python3 -c "import json; print(json.load(open('$SECRETS'))['origin'])")

# 2) Claves de Garmin y Anthropic en SSM (SecureString), sin mostrarlas
aws ssm put-parameter --name /garmin-stats/garmin-key --type SecureString --overwrite \
  --value "file://$HOME/.config/garmin/connect-personal-api-key" >/dev/null
aws ssm put-parameter --name /garmin-stats/anthropic-key --type SecureString --overwrite \
  --value "file://$HOME/.config/anthropic/garmin-stats-key" >/dev/null
# Cliente OAuth de Google, si ya está guardado en local. Acepta el JSON tal cual lo descarga Google
# ({"web": {"client_id", "client_secret", ...}}) o uno simple {"client_id", "client_secret"}.
GJSON=~/.config/garmin/google-oauth.json
if [ -f "$GJSON" ]; then
  chmod 600 "$GJSON"
  gfield() { python3 -c "import json,sys; d=json.load(open(sys.argv[1])); d=d.get('web', d); print(d[sys.argv[2]], end='')" "$GJSON" "$1"; }
  aws ssm put-parameter --name /garmin-stats/google-client-id --type String --overwrite --value "$(gfield client_id)" >/dev/null
  umask 077; gfield client_secret > /tmp/.gs-gsec
  aws ssm put-parameter --name /garmin-stats/google-client-secret --type SecureString --overwrite --value file:///tmp/.gs-gsec >/dev/null
  rm -f /tmp/.gs-gsec
  echo "Cliente OAuth de Google guardado en SSM."
fi

# Claves VAPID para las notificaciones push (se crean una vez)
VAPID=~/.config/garmin/vapid.json
if [ ! -f "$VAPID" ]; then
  umask 077
  uv run --quiet --no-project --with cryptography python - "$VAPID" <<'PY'
import base64, json, sys
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
k = ec.generate_private_key(ec.SECP256R1())
b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()
der = k.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
pub = k.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
json.dump({"private": b64(der), "public": b64(pub)}, open(sys.argv[1], "w"))
PY
fi
VAPID_PUBLIC=$(python3 -c "import json; print(json.load(open('$VAPID'))['public'])")
python3 -c "import json; print(json.load(open('$VAPID'))['private'], end='')" > /tmp/.gs-vapid && chmod 600 /tmp/.gs-vapid
aws ssm put-parameter --name /garmin-stats/vapid-private --type SecureString --overwrite --value file:///tmp/.gs-vapid >/dev/null
rm -f /tmp/.gs-vapid

# 3) Bucket de artefactos (código de las Lambda)
if ! aws s3api head-bucket --bucket "$ARTIFACTS" 2>/dev/null; then
  aws s3api create-bucket --bucket "$ARTIFACTS" --create-bucket-configuration LocationConstraint="$AWS_REGION" >/dev/null
  aws s3api put-public-access-block --bucket "$ARTIFACTS" \
    --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
fi

# 4) Paquete de la API: dependencias para Lambda (Linux x86_64, Python 3.12) + código del proyecto
rm -rf infra/build && mkdir -p infra/build/api
uv pip install --quiet --target infra/build/api --python-version 3.12 --python-platform x86_64-manylinux_2_28 \
  --only-binary :all: "anthropic>=2.3" "pydantic>=2"
cp -r src/garmin_stats infra/build/api/ && find infra/build/api -name __pycache__ -prune -exec rm -rf {} +
cp infra/lambda/api/handler.py infra/build/api/
# Paquete de la sincronización: todas las dependencias del proyecto (pandas, fitdecode, cliente de Garmin...)
mkdir -p infra/build/sync
# Binarios para Linux siempre que existan; los paquetes de Python puro sin binario (http-ece) se compilan.
uv pip install --quiet --target infra/build/sync --python-version 3.12 --python-platform x86_64-manylinux_2_28 \
  --only-binary pandas --only-binary numpy --only-binary pydantic-core --only-binary cryptography --only-binary cffi \
  "anthropic>=2.3" "pydantic>=2" "pandas>=2.3" "fitdecode>=0.10" "garmin-connect-personal-api-python>=1.0" \
  "pywebpush>=2"
cp -r src/garmin_stats infra/build/sync/ && cp infra/lambda/sync/handler.py infra/lambda/sync/notify.py infra/build/sync/
find infra/build/sync \( -name __pycache__ -o -name tests \) -prune -exec rm -rf {} + 2>/dev/null || true
echo "Tamaño del paquete de sincronización: $(du -sh infra/build/sync | cut -f1)"
cp infra/stack.yaml infra/build/stack.yaml && cp -r infra/lambda infra/build/lambda

# 5) Empaquetar y desplegar
aws cloudformation package --template-file infra/build/stack.yaml --s3-bucket "$ARTIFACTS" --s3-prefix lambda \
  --output-template-file infra/build/packaged.yaml >/dev/null
aws cloudformation deploy --stack-name "$STACK" --template-file infra/build/packaged.yaml \
  --capabilities CAPABILITY_IAM --no-fail-on-empty-changeset \
  --parameter-overrides AllowedEmails="$EMAIL" BudgetEmail="$EMAIL" SessionSecret="$SESSION" OriginSecret="$ORIGIN" VapidPublicKey="$VAPID_PUBLIC"

out() { aws cloudformation describe-stacks --stack-name "$STACK" --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text; }
BUCKET=$(out Bucket); URL=$(out Url)

# 6) Si hay una versión nueva de la web compilada (web → site/index.html), se publica. Los datos (data.js,
#    detalles, estado) solo los escribe la Lambda de sincronización: nunca se suben desde el PC.
if [ -f site/index.html ]; then
  aws s3 cp site/index.html "s3://$BUCKET/site/index.html" --content-type "text/html; charset=utf-8" \
    --cache-control no-store --only-show-errors
  # Archivos de la app instalable (manifiesto, service worker, iconos)
  [ -f site/manifest.webmanifest ] && aws s3 cp site/manifest.webmanifest "s3://$BUCKET/site/manifest.webmanifest" \
    --content-type application/manifest+json --cache-control no-cache --only-show-errors
  [ -f site/sw.js ] && aws s3 cp site/sw.js "s3://$BUCKET/site/sw.js" --content-type "text/javascript; charset=utf-8" \
    --cache-control no-cache --only-show-errors
  [ -d site/icons ] && aws s3 sync site/icons "s3://$BUCKET/site/icons/" --cache-control "max-age=604800" --only-show-errors
fi
# Icono de la pantalla de inicio en las rutas estándar (el iPhone las pide por su cuenta)
for f in apple-touch-icon.png apple-touch-icon-precomposed.png favicon.ico; do
  aws s3 cp web/public/icons/apple-touch-icon.png "s3://$BUCKET/site/$f" --content-type image/png \
    --cache-control "max-age=604800" --only-show-errors
done
if false; then :
  aws lambda invoke --function-name garmin-stats-sync --invocation-type Event /dev/null >/dev/null  # refresca data.js
  echo "Web publicada; la sincronización actualiza los datos en ~30 s."
fi
echo
echo "Web:              $URL"
echo "Redirección OAuth: $(out GoogleRedirectUri)"
