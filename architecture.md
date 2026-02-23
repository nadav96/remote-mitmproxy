# Architecture

```mermaid
graph TB
    subgraph Internet
        User["👤 You / Your Device"]
    end

    subgraph AWS["☁️ AWS Cloud"]

        subgraph VPC["🔒 VPC (Private Network - 10.0.0.0/16)"]

            subgraph SubnetA["Subnet A (10.0.1.0/24)"]
                EC2["🖥️ EC2 Instance<br/>(Virtual Server)<br/>runs Docker + Nginx"]
                EIP["📌 Elastic IP<br/>(Static Public IP)"]
            end

            subgraph SubnetB["Subnet B (10.0.2.0/24)"]
            end

            ALB["⚖️ ALB<br/>(Load Balancer)<br/>Terminates HTTPS"]

            EC2SG["🛡️ EC2 Security Group<br/>(Firewall for EC2)<br/>Allows: 8080, 8081 from ALB only<br/>Allows: 22 from anywhere"]
            ALBSG["🛡️ ALB Security Group<br/>(Firewall for ALB)<br/>Allows: 443 from anywhere"]

            RouteTable["🗺️ Route Table<br/>(Network traffic rules)"]
        end

        IGW["🌐 Internet Gateway<br/>(Door to the internet)"]
        ACM["📜 ACM Certificate<br/>(*.example.com SSL cert)"]

        IAMRole["🔑 IAM Role<br/>(Permissions for EC2)<br/>SSM + S3 read"]
        IAMProfile["📋 Instance Profile<br/>(Attaches role to EC2)"]
    end

    subgraph EC2Inside["Inside the EC2 Instance"]
        Docker["🐳 Docker Container<br/>mitmproxy/mitmweb<br/>Port 8080 = proxy<br/>Port 8082 = web UI"]
        Nginx["📡 Nginx<br/>Port 8081<br/>Basic auth + reverse proxy<br/>to mitmweb on 8082"]
        Addon["🐍 addon.py<br/>(Your Python script)<br/>Downloaded from S3"]
    end

    subgraph ALBInside["Inside the ALB"]
        Listener["👂 HTTPS Listener<br/>Port 443<br/>Uses ACM cert"]
        ProxyRule["📋 Listener Rule<br/>Host = proxy.example.com<br/>→ Proxy Target Group"]
        DefaultAction["📋 Default Action<br/>Everything else<br/>→ Web Target Group"]
        ProxyTG["🎯 Proxy Target Group<br/>→ EC2:8080 (mitmproxy)"]
        WebTG["🎯 Web Target Group<br/>→ EC2:8081 (nginx)"]
    end

    %% User traffic flows
    User -->|"https://proxy.example.com<br/>(proxied traffic)"| ALB
    User -->|"https://mitmweb.example.com<br/>(web UI)"| ALB
    User -->|"SSH (port 22)"| EC2

    %% ALB routing
    ALB --> Listener
    Listener --> ProxyRule
    Listener --> DefaultAction
    ProxyRule --> ProxyTG
    DefaultAction --> WebTG
    ProxyTG -->|"HTTP :8080"| Docker
    WebTG -->|"HTTP :8081"| Nginx
    Nginx -->|"HTTP :8082"| Docker

    %% Network connections
    IGW --- VPC
    RouteTable -->|"0.0.0.0/0 → Internet"| IGW
    RouteTable --- SubnetA
    RouteTable --- SubnetB
    EIP --- EC2

    %% Security
    ALBSG -.->|"protects"| ALB
    EC2SG -.->|"protects"| EC2
    ACM -.->|"provides cert"| Listener
    IAMRole --- IAMProfile
    IAMProfile -.->|"attached to"| EC2

    %% Upstream
    Docker -->|"Forwards request to<br/>upstream server"| Internet

    style VPC fill:#e8f4f8,stroke:#2196F3
    style SubnetA fill:#e8f8e8,stroke:#4CAF50
    style SubnetB fill:#e8f8e8,stroke:#4CAF50
    style EC2Inside fill:#fff3e0,stroke:#FF9800
    style ALBInside fill:#fce4ec,stroke:#E91E63
    style Internet fill:#f3e5f5,stroke:#9C27B0
```

## How it works (in plain English)

1. **VPC** = Your own private network in AWS. Nothing gets in or out unless you allow it.
2. **Subnets** = Smaller sections of the VPC. The ALB needs at least 2 in different zones (for redundancy).
3. **Internet Gateway** = The "door" connecting your VPC to the public internet.
4. **Route Table** = Rules that say "traffic going to the internet → use the Internet Gateway".
5. **ALB (Load Balancer)** = The front door for HTTPS traffic. It holds the SSL certificate and decides where to send requests based on the domain name.
6. **HTTPS Listener** = Listens on port 443, uses the ACM certificate.
7. **Listener Rule** = If the request is for `proxy.example.com` → send to mitmproxy. Otherwise → send to mitmweb (nginx).
8. **Target Groups** = "Address books" telling the ALB which port on the EC2 to forward to.
9. **Security Groups** = Firewalls. The ALB allows port 443 from anywhere. The EC2 only allows traffic from the ALB (except SSH).
10. **EC2 Instance** = The virtual server running everything.
11. **Elastic IP** = A fixed public IP so SSH always works at the same address.
12. **IAM Role + Profile** = Permissions allowing the EC2 to download your addon script from S3.
13. **Nginx** = Adds username/password protection in front of the mitmweb UI.
14. **mitmproxy (Docker)** = The actual proxy that intercepts and displays traffic, running your `addon.py` script.
