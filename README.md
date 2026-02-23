# Remote mitmproxy

A CloudFormation-based project (using [RocketSam](https://www.npmjs.com/package/rocketsam)) that deploys a remote [mitmproxy](https://mitmproxy.org/) instance on AWS. Traffic goes through an ALB with a **valid ACM certificate**, so clients trust the HTTPS connection without installing any CA certificate.

## Architecture

See [architecture.md](architecture.md) for a full diagram.

- **ALB (HTTPS :443)** — Terminates TLS using an ACM certificate. Routes traffic by hostname:
  - `proxy.<your-domain>` → mitmproxy (port 8080)
  - Everything else → mitmweb UI via Nginx (port 8081, basic auth)
- **EC2** — Runs a Docker container with mitmweb + an optional Python addon script.
- **Nginx** — Reverse proxy with basic auth protecting the mitmweb UI.

## Prerequisites

- [RocketSam CLI](https://www.npmjs.com/package/rocketsam) (`npm i -g rocketsam`)
- [AWS SAM CLI](https://aws.amazon.com/serverless/sam/)
- AWS CLI configured with credentials
- An **ACM certificate** for your domain (e.g. `*.example.com`)
- An **EC2 key pair** in the target region
- An **S3 bucket** for storing the addon script and deployment artifacts

## Setup

### 1. Create SSM parameters for credentials

The web UI credentials are stored in AWS SSM Parameter Store (SecureString), not in the template.

```bash
aws ssm put-parameter \
  --name "/remote-mitmproxy/WebUsername" \
  --value "your-username" \
  --type SecureString \
  --region us-east-1

aws ssm put-parameter \
  --name "/remote-mitmproxy/WebPassword" \
  --value "your-secure-password" \
  --type SecureString \
  --region us-east-1
```

### 2. Configure the template

Edit `app/template-skeleton.yaml` and set the parameter defaults:

| Parameter | What to set |
|---|---|
| `KeyPairName` | Your EC2 key pair name |
| `CertificateId` | The UUID from your ACM certificate ARN |
| `ProxyHostname` | e.g. `proxy.example.com` |
| `UpstreamUrl` | e.g. `https://upstream.example.com` (for reverse mode) |
| `ScriptsBucket` | Your S3 bucket name |
| `AmiId` | Amazon Linux 2023 AMI for your region |

### 3. Configure RocketSam

Edit `rocketsam.yaml` and set:
- `storageBucketName` — your S3 bucket
- `stackName` — your CloudFormation stack name
- `region` — your AWS region

### 4. Deploy

```bash
# Upload addon script to S3, build template, and deploy
./deploy.sh
```

Or manually:

```bash
# Upload addon script
aws s3 cp app/scripts/addon.py s3://<your-bucket>/remote-mitmproxy/scripts/addon.py

# Build and deploy
rocketsam template
rocketsam deploy
```

### 5. DNS setup

After deployment, run `rocketsam outputs` to get the ALB DNS name. Create CNAME records:

- `proxy.example.com` → `<ALB DNS name>`
- `mitmweb.example.com` → `<ALB DNS name>` (optional, for the web UI)

## Usage

- **Proxy endpoint**: `https://proxy.<your-domain>` — point your client here
- **Web UI**: Open the `MitmwebURL` from stack outputs, login with your SSM credentials
- **SSH**: Use the `SSHCommand` from stack outputs

## Forcing EC2 replacement

To re-run UserData (e.g. after changing the addon script or Docker image), toggle the `InstanceSubnet` parameter between `A` and `B` in `app/template-skeleton.yaml`, then redeploy. This forces CloudFormation to create a fresh EC2 instance.

## Addon script

The `app/scripts/addon.py` is a mitmproxy addon that rewrites OAuth redirect URIs and response Location headers between your proxy domain and the upstream host. Edit `PROXY_HOST` and `TARGET_HOST` in the script to match your setup.

## Troubleshooting

```bash
# SSH into the instance
ssh -i <your-key>.pem ec2-user@<EIP>

# Check user-data log
cat /var/log/user-data.log

# Check Docker container
sudo docker ps
sudo docker logs mitmproxy

# Check nginx
systemctl status nginx

# Restart mitmproxy
sudo docker restart mitmproxy
```

## Cleanup

```bash
rocketsam remove
```
