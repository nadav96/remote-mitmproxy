# Architecture

```mermaid
graph TB
    subgraph Internet
        User["👤 You / Your Device"]
        Cloudflare["☁️ Cloudflare<br/>Terminates TLS<br/>(free HTTPS cert)"]
    end

    subgraph AWS["☁️ AWS Cloud"]

        subgraph VPC["🔒 VPC (10.0.0.0/16)"]

            subgraph SubnetA["Subnet A (10.0.1.0/24)"]
                EC2["🖥️ EC2 Instance<br/>runs Docker + Nginx"]
                EIP["📌 Elastic IP<br/>(Static Public IP)"]
            end

            subgraph SubnetB["Subnet B (10.0.2.0/24)"]
            end

            EC2SG["🛡️ Security Group<br/>Allows: 80 from anywhere<br/>Allows: 22 from anywhere"]

            RouteTable["🗺️ Route Table"]
        end

        IGW["🌐 Internet Gateway"]

        IAMRole["🔑 IAM Role<br/>(SSM + S3 read)"]
        IAMProfile["📋 Instance Profile"]
    end

    subgraph EC2Inside["Inside the EC2 Instance"]
        Nginx["📡 Nginx (port 80)<br/>Routes by hostname:<br/>proxy.* → mitmproxy<br/>* → mitmweb (basic auth)"]
        Docker["🐳 Docker Container<br/>mitmproxy/mitmweb<br/>Port 8080 = proxy<br/>Port 8082 = web UI"]
        Addon["🐍 addon.py<br/>Downloaded from S3"]
    end

    %% Traffic flow
    User -->|"HTTPS"| Cloudflare
    Cloudflare -->|"HTTP :80"| EIP
    User -->|"SSH :22"| EIP
    EIP --- EC2

    %% Nginx routing
    Nginx -->|"proxy.example.com<br/>→ :8080"| Docker
    Nginx -->|"*.example.com<br/>→ :8082 (basic auth)"| Docker

    %% Network
    IGW --- VPC
    RouteTable -->|"0.0.0.0/0 → IGW"| IGW
    RouteTable --- SubnetA
    RouteTable --- SubnetB

    %% Security
    EC2SG -.->|"protects"| EC2
    IAMRole --- IAMProfile
    IAMProfile -.->|"attached to"| EC2

    %% Upstream
    Docker -->|"Forwards to upstream"| Internet

    style VPC fill:#e8f4f8,stroke:#2196F3
    style SubnetA fill:#e8f8e8,stroke:#4CAF50
    style SubnetB fill:#e8f8e8,stroke:#4CAF50
    style EC2Inside fill:#fff3e0,stroke:#FF9800
    style Internet fill:#f3e5f5,stroke:#9C27B0
```

## How it works

1. **Cloudflare** terminates TLS — you get a valid HTTPS cert without ACM or an ALB.
2. **Elastic IP** gives the EC2 a fixed public address. Point Cloudflare DNS (proxied) at it.
3. **Nginx (port 80)** routes by hostname:
   - `proxy.example.com` → mitmproxy on port 8080 (the actual intercepting proxy)
   - Everything else → mitmweb UI on port 8082 (with basic auth)
4. **Docker** runs mitmweb which provides both the proxy (8080) and web UI (8081, mapped to 8082 on host).
5. **Security Group** only exposes port 80 (HTTP from Cloudflare) and port 22 (SSH).
6. **IAM Role** lets the EC2 fetch credentials from SSM and the addon script from S3.
