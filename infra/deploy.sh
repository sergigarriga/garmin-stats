#!/usr/bin/env bash
# Despliega la web privada en AWS (cuenta personal, perfil `default`) con un único stack.
# Uso: infra/deploy.sh            (idempotente: se puede relanzar para actualizar)
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

# 2) Clave de Anthropic en SSM (SecureString), sin mostrarla
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
cp infra/stack.yaml infra/build/stack.yaml && cp -r infra/lambda infra/build/lambda

# 5) Empaquetar y desplegar
aws cloudformation package --template-file infra/build/stack.yaml --s3-bucket "$ARTIFACTS" --s3-prefix lambda \
  --output-template-file infra/build/packaged.yaml >/dev/null
aws cloudformation deploy --stack-name "$STACK" --template-file infra/build/packaged.yaml \
  --capabilities CAPABILITY_IAM --no-fail-on-empty-changeset \
  --parameter-overrides AllowedEmails="$EMAIL" BudgetEmail="$EMAIL" SessionSecret="$SESSION" OriginSecret="$ORIGIN"

out() { aws cloudformation describe-stacks --stack-name "$STACK" --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text; }
BUCKET=$(out Bucket); URL=$(out Url)
printf '{"bucket": "%s", "url": "%s", "region": "%s", "profile": "%s"}\n' "$BUCKET" "$URL" "$AWS_REGION" "$AWS_PROFILE" > data/aws.json

# 6) Subir la web y el estado
bin/aws-sync.sh up
echo
echo "Web:              $URL"
echo "Redirección OAuth: $(out GoogleRedirectUri)"
