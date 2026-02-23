# Remote mitmproxy

A RocketSam project that deploys an EC2 instance running [mitmproxy](https://mitmproxy.org/) with a web UI (mitmweb), fronted by an ALB with a valid HTTPS certificate.

## Architecture

```
Device                          Browser
  │                               │
  │ proxy (port 8080)             │ HTTPS :443
  ▼                               ▼
┌──────────┐               ┌─────────────┐
│ EC2:8080 │               │  ALB (ACM)  │
│ mitmproxy│               └──────┬──────┘
│ (Docker) │                      │ HTTP :8081
│          │               ┌──────▼──────┐
│          │               │   Nginx     │
│          │               │ (basic auth)│
│          │               └──────┬──────┘
│          │                      │ :8082
│          │               ┌──────▼──────┐
│          │◄──────────────│   mitmweb   │
│          │  same container (localhost)  │
└──────────┘               └─────────────┘
```

- **Port 8080** — mitmproxy listener. Devices connect here (no auth).
- **ALB :443** — HTTPS with ACM certificate → Nginx :8081 (basic auth) → mitmweb :8082 (localhost only).
- **SSH :22** — for management and downloading the CA certificate.

## Prerequisites

- [RocketSam CLI](https://www.npmjs.com/package/rocketsam) installed (`npm i -g rocketsam`)
- [AWS SAM CLI](https://aws.amazon.com/serverless/sam/)
- AWS CLI configured with appropriate credentials
- An **ACM certificate** in the same region (for ALB HTTPS)
- An **EC2 key pair** in the same region
- A **VPC** with at least 2 public subnets in different AZs

## Parameters

| Parameter | Default | Description |
|---|---|---|
| `VpcId` | — | VPC to deploy into |
| `SubnetId` | — | Public subnet for the EC2 instance |
| `ALBSubnetIds` | — | ≥2 subnets in different AZs for the ALB |
| `InstanceType` | `t3.small` | EC2 instance type |
| `KeyPairName` | — | SSH key pair name |
| `CertificateArn` | — | ACM certificate ARN |
| `WebUsername` | `admin` | mitmweb basic-auth username |
| `WebPassword` | — | mitmweb basic-auth password (min 8 chars) |
| `ProxyMode` | `regular` | `regular` (forward proxy) or `reverse` |
| `UpstreamUrl` | — | Upstream URL for reverse mode (e.g. `https://example.com`) |

## Deploy

```bash
# Build the SAM template
rocketsam build all

# Deploy (you will be prompted for parameters)
rocketsam deploy
```

If `rocketsam deploy` doesn't prompt for parameters, pass them via the AWS CLI after building:

```bash
aws cloudformation deploy \
  --template-file .build/template.yaml \
  --stack-name remote-mitmproxy \
  --capabilities CAPABILITY_IAM \
  --region eu-west-1 \
  --parameter-overrides \
    VpcId=vpc-xxxxxxxx \
    SubnetId=subnet-xxxxxxxx \
    ALBSubnetIds=subnet-aaaa,subnet-bbbb \
    KeyPairName=my-key \
    CertificateArn=arn:aws:acm:eu-west-1:123456789012:certificate/xxxxxxxx \
    WebPassword=MySecurePass123
```

## Usage

### 1. Get stack outputs

```bash
rocketsam outputs
```

This shows:
- **ProxyEndpoint** — `<EIP>:8080` (configure on your device)
- **MitmwebURL** — `https://<alb-dns>` (open in browser, login required)
- **SSHCommand** / **DownloadCACert** — helper commands

### 2. Install the CA certificate on your device

mitmproxy generates a CA certificate on first run. You need to install it on your device to intercept HTTPS traffic.

```bash
# Download from the EC2 instance
scp -i <your-key>.pem ec2-user@<EIP>:/opt/mitmproxy/mitmproxy-ca-cert.pem .

# Install on macOS
sudo security add-trusted-cert -d -r trustRoot \
  -k /Library/Keychains/System.keychain mitmproxy-ca-cert.pem
```

For iOS/Android, transfer the `.pem` file and install it via Settings → Certificates.

### 3. Configure your device proxy

Point your device's HTTP proxy settings to the EC2 Elastic IP on port **8080**.

### 4. View traffic

Open the **MitmwebURL** from the stack outputs in your browser. Log in with the `WebUsername` / `WebPassword` you set during deployment.

## Proxy Modes

- **regular** (default) — Standard forward proxy. Configure your device to use `<EIP>:8080` as its HTTP/HTTPS proxy.
- **reverse** — Reverse proxy for a specific upstream. Set `UpstreamUrl` to the target (e.g. `https://api.example.com`). Clients connect to `<EIP>:8080` and traffic is forwarded to the upstream.

## Troubleshooting

```bash
# SSH into the instance
ssh -i <your-key>.pem ec2-user@<EIP>

# Check user-data log
cat /var/log/user-data.log

# Check Docker container
docker ps
docker logs mitmproxy

# Check nginx
systemctl status nginx
journalctl -u nginx

# Restart mitmproxy
docker restart mitmproxy
```

## Cleanup

```bash
aws cloudformation delete-stack --stack-name remote-mitmproxy --region eu-west-1
```
