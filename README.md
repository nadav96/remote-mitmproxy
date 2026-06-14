# Remote mitmproxy

A CloudFormation-based project (using [RocketSam](https://www.npmjs.com/package/rocketsam)) that deploys a remote [mitmproxy](https://mitmproxy.org/) instance on AWS. TLS is terminated by **Cloudflare** — no ALB or ACM certificate needed.

## Architecture

See [architecture.md](architecture.md) for a full diagram.

- **Cloudflare** — Terminates TLS, provides a valid HTTPS cert. DNS records (proxied) point at the EC2 Elastic IP.
- **EC2** — Runs a Docker container with mitmweb + an optional Python addon script.
- **Nginx (port 80)** — Routes by hostname:
  - `proxy.<your-domain>` → mitmproxy (port 8080)
  - Everything else → mitmweb UI (port 8082, basic auth)

## Prerequisites

- [RocketSam CLI](https://www.npmjs.com/package/rocketsam) (`npm i -g rocketsam`)
- [AWS SAM CLI](https://aws.amazon.com/serverless/sam/)
- AWS CLI configured with credentials
- A **Cloudflare** account with your domain
- An **EC2 key pair** in the target region
- An **S3 bucket** for storing the addon script and deployment artifacts

## Setup

### 1. Create SSM parameters for credentials

The web UI credentials are stored in AWS SSM Parameter Store (SecureString).

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
./deploy.sh
```

Or manually:

```bash
aws s3 cp app/scripts/addon.py s3://<your-bucket>/remote-mitmproxy/scripts/addon.py
rocketsam template
rocketsam deploy
```

### 5. Cloudflare DNS setup

After deployment, run `rocketsam outputs` to get the Elastic IP. Create **proxied** DNS records in Cloudflare:

- `proxy.example.com` → `<Elastic IP>` (A record, proxied)
- `mitmweb.example.com` → `<Elastic IP>` (A record, proxied)

Make sure Cloudflare SSL mode is set to **Flexible** (Cloudflare terminates TLS, connects to origin over HTTP).

## Usage

- **Proxy endpoint**: `https://proxy.<your-domain>` — point your client here
- **Web UI**: `https://mitmweb.<your-domain>` — login with your SSM credentials
- **SSH**: Use the `SSHCommand` from stack outputs

## Forcing EC2 replacement

To re-run UserData (e.g. after changing the addon script or Docker image), toggle the `InstanceSubnet` parameter between `A` and `B` in `app/template-skeleton.yaml`, then redeploy.

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
nginx -t

# Restart mitmproxy
sudo docker restart mitmproxy
```

## Cleanup

```bash
rocketsam remove
```
