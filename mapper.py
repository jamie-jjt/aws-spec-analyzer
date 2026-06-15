"""
mapper.py - Parses technical specification text and maps requirements to AWS services.

This module handles:
- On-prem hardware → AWS equivalent mapping
- Other cloud (Azure, GCP) → AWS equivalent mapping
- Compute, storage, networking, database, analytics, AI/ML, containers, etc.
- Confidence scoring and "need more info" detection
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional
from pricing import apply_region, get_multiplier, all_regions, REGION_LABELS


@dataclass
class SpecRequirement:
    """A single parsed requirement extracted from the spec."""
    category: str           # e.g., "Compute", "Storage", "Database"
    raw_description: str    # original text snippet
    quantity: int = 1
    unit: str = ""          # e.g., "vCPU", "GB", "TB", "IOPS", "Mbps"
    value: float = 0.0
    source_platform: str = "generic"  # "onprem", "azure", "gcp", "generic"
    notes: str = ""


@dataclass
class AWSServiceMapping:
    """An AWS service recommendation for a given requirement."""
    requirement: SpecRequirement
    service_name: str           # e.g., "Amazon EC2"
    service_code: str           # e.g., "AmazonEC2"
    recommended_type: str       # e.g., "m7g.xlarge"
    description: str
    quantity: int = 1
    unit: str = "instance"
    confidence: str = "high"    # "high", "medium", "low", "needs_info"
    missing_info: List[str] = field(default_factory=list)
    alternatives: List[dict] = field(default_factory=list)
    pricing_options: List[str] = field(default_factory=list)
    monthly_estimate_usd: float = 0.0
    base_monthly_usd: float = 0.0  # us-east-1 price before region multiplier
    aws_calculator_url: str = ""
    region: str = "us-east-1"
    reasoning: str = ""


# ── Cloud vendor translation dictionaries ─────────────────────────────────────

AZURE_TO_AWS = {
    # Compute
    "azure vm": "Amazon EC2",
    "virtual machine": "Amazon EC2",
    "vmss": "Amazon EC2 Auto Scaling",
    "scale set": "Amazon EC2 Auto Scaling",
    "azure kubernetes service": "Amazon EKS",
    "aks": "Amazon EKS",
    "azure container instances": "AWS Fargate",
    "aci": "AWS Fargate",
    "azure functions": "AWS Lambda",
    "app service": "AWS Elastic Beanstalk",
    "azure batch": "AWS Batch",
    # Storage
    "azure blob storage": "Amazon S3",
    "blob storage": "Amazon S3",
    "azure files": "Amazon EFS",
    "azure disk": "Amazon EBS",
    "managed disk": "Amazon EBS",
    "azure data lake": "Amazon S3 + AWS Lake Formation",
    "azure netapp files": "Amazon FSx for NetApp ONTAP",
    # Database
    "azure sql": "Amazon RDS for SQL Server",
    "azure sql database": "Amazon RDS for SQL Server",
    "azure database for postgresql": "Amazon RDS for PostgreSQL",
    "azure database for mysql": "Amazon RDS for MySQL",
    "cosmos db": "Amazon DynamoDB",
    "azure cosmos db": "Amazon DynamoDB",
    "azure cache for redis": "Amazon ElastiCache for Redis",
    "azure synapse": "Amazon Redshift",
    "azure data factory": "AWS Glue",
    # Networking
    "azure load balancer": "Elastic Load Balancing",
    "application gateway": "AWS Application Load Balancer",
    "azure cdn": "Amazon CloudFront",
    "azure dns": "Amazon Route 53",
    "virtual network": "Amazon VPC",
    "vnet": "Amazon VPC",
    "azure vpn gateway": "AWS Site-to-Site VPN",
    "expressroute": "AWS Direct Connect",
    "azure firewall": "AWS Network Firewall",
    # Monitoring & Management
    "azure monitor": "Amazon CloudWatch",
    "azure log analytics": "Amazon CloudWatch Logs",
    "azure active directory": "AWS IAM Identity Center",
    "azure key vault": "AWS Secrets Manager",
    "azure devops": "AWS CodePipeline",
    # AI/ML
    "azure openai": "Amazon Bedrock",
    "azure cognitive services": "Amazon Rekognition / Amazon Comprehend",
    "azure machine learning": "Amazon SageMaker",
    "azure search": "Amazon OpenSearch Service",
    # Messaging
    "azure service bus": "Amazon SQS / Amazon SNS",
    "azure event hub": "Amazon Kinesis",
    "azure event grid": "Amazon EventBridge",
    "azure notification hubs": "Amazon SNS",
}

GCP_TO_AWS = {
    # Compute
    "google compute engine": "Amazon EC2",
    "gce": "Amazon EC2",
    "google kubernetes engine": "Amazon EKS",
    "gke": "Amazon EKS",
    "cloud run": "AWS Fargate / AWS App Runner",
    "cloud functions": "AWS Lambda",
    "app engine": "AWS Elastic Beanstalk",
    "cloud batch": "AWS Batch",
    # Storage
    "google cloud storage": "Amazon S3",
    "gcs": "Amazon S3",
    "persistent disk": "Amazon EBS",
    "filestore": "Amazon EFS",
    "cloud spanner": "Amazon Aurora",
    # Database
    "cloud sql": "Amazon RDS",
    "cloud bigtable": "Amazon DynamoDB",
    "firestore": "Amazon DynamoDB",
    "bigquery": "Amazon Redshift",
    "cloud dataflow": "AWS Glue / Amazon Kinesis Data Firehose",
    "cloud dataproc": "Amazon EMR",
    "memorystore": "Amazon ElastiCache",
    # Networking
    "cloud load balancing": "Elastic Load Balancing",
    "cloud cdn": "Amazon CloudFront",
    "cloud dns": "Amazon Route 53",
    "vpc": "Amazon VPC",
    "cloud vpn": "AWS Site-to-Site VPN",
    "cloud interconnect": "AWS Direct Connect",
    "cloud armor": "AWS WAF + AWS Shield",
    # AI/ML
    "vertex ai": "Amazon SageMaker",
    "cloud vision": "Amazon Rekognition",
    "cloud natural language": "Amazon Comprehend",
    "dialogflow": "Amazon Lex",
    "cloud translation": "Amazon Translate",
    # Messaging
    "cloud pub/sub": "Amazon SNS + Amazon SQS",
    "cloud tasks": "Amazon SQS",
    "eventarc": "Amazon EventBridge",
    # Monitoring
    "cloud monitoring": "Amazon CloudWatch",
    "cloud logging": "Amazon CloudWatch Logs",
    "secret manager": "AWS Secrets Manager",
    "cloud iam": "AWS IAM",
}

ONPREM_TO_AWS = {
    # Compute / Servers
    "physical server": "Amazon EC2",
    "bare metal": "Amazon EC2 Bare Metal",
    "blade server": "Amazon EC2",
    "rack server": "Amazon EC2",
    "vmware": "Amazon EC2 / VMware Cloud on AWS",
    "hyper-v": "Amazon EC2",
    "kvm": "Amazon EC2",
    "virtualbox": "Amazon EC2",
    # Storage
    "san": "Amazon EBS",
    "nas": "Amazon EFS / Amazon FSx",
    "nfs": "Amazon EFS",
    "smb": "Amazon FSx for Windows File Server",
    "cifs": "Amazon FSx for Windows File Server",
    "tape backup": "Amazon S3 Glacier",
    "object storage": "Amazon S3",
    "block storage": "Amazon EBS",
    "file storage": "Amazon EFS",
    "netapp": "Amazon FSx for NetApp ONTAP",
    "pure storage": "Amazon EBS io2",
    # Networking
    "load balancer": "Elastic Load Balancing",
    "firewall": "AWS Network Firewall",
    "web application firewall": "AWS WAF",
    "waf": "AWS WAF",
    "vpn": "AWS Site-to-Site VPN",
    "mpls": "AWS Direct Connect",
    "wan": "AWS Transit Gateway",
    "dns server": "Amazon Route 53",
    "cdn": "Amazon CloudFront",
    # Database
    "oracle database": "Amazon RDS for Oracle / Amazon Aurora",
    "oracle": "Amazon RDS for Oracle",
    "sql server": "Amazon RDS for SQL Server",
    "mysql": "Amazon RDS for MySQL",
    "postgresql": "Amazon RDS for PostgreSQL",
    "mariadb": "Amazon RDS for MariaDB",
    "redis": "Amazon ElastiCache for Redis",
    "memcached": "Amazon ElastiCache for Memcached",
    "mongodb": "Amazon DocumentDB",
    "cassandra": "Amazon Keyspaces",
    "elasticsearch": "Amazon OpenSearch Service",
    # Messaging / Integration
    "rabbitmq": "Amazon MQ",
    "activemq": "Amazon MQ",
    "kafka": "Amazon MSK",
    "ibm mq": "Amazon MQ",
    # Monitoring
    "monitoring server": "Amazon CloudWatch",
    "logging server": "Amazon CloudWatch Logs",
    "syslog": "Amazon CloudWatch Logs",
    # Identity
    "active directory": "AWS Directory Service / AWS IAM Identity Center",
    "ldap": "AWS Directory Service",
    "radius": "AWS IAM",
    # HPC / GPU
    "gpu server": "Amazon EC2 (P/G/Inf instances)",
    "hpc cluster": "AWS ParallelCluster",
    # Containers
    "docker": "Amazon ECS / Amazon EKS",
    "kubernetes": "Amazon EKS",
    "openshift": "Amazon EKS / Amazon Rosa",
}

# ── EC2 instance sizing heuristics ────────────────────────────────────────────

# Maps (vCPU, RAM_GB) → (instance_family, x86_type, graviton_type)
EC2_SIZE_MAP = [
    # (min_vcpu, min_ram_gb, x86_type, graviton_type, family)
    (1,   0.5,  "t3.micro",     "t4g.micro",    "General Purpose"),
    (1,   1,    "t3.small",     "t4g.small",    "General Purpose"),
    (2,   4,    "t3.medium",    "t4g.medium",   "General Purpose"),
    (2,   8,    "m6i.large",    "m7g.large",    "General Purpose"),
    (4,   16,   "m6i.xlarge",   "m7g.xlarge",   "General Purpose"),
    (8,   32,   "m6i.2xlarge",  "m7g.2xlarge",  "General Purpose"),
    (16,  64,   "m6i.4xlarge",  "m7g.4xlarge",  "General Purpose"),
    (32,  128,  "m6i.8xlarge",  "m7g.8xlarge",  "General Purpose"),
    (48,  192,  "m6i.12xlarge", "m7g.12xlarge", "General Purpose"),
    (64,  256,  "m6i.16xlarge", "m7g.16xlarge", "General Purpose"),
    (96,  384,  "m6i.24xlarge", "m7g.24xlarge", "General Purpose"),
    (128, 512,  "m6i.32xlarge", "m7g.metal",    "General Purpose"),
]

# Rough on-demand monthly prices (USD) for us-east-1
EC2_MONTHLY_PRICES = {
    "t3.micro": 8.47, "t4g.micro": 7.59,
    "t3.small": 16.93, "t4g.small": 15.18,
    "t3.medium": 33.87, "t4g.medium": 30.37,
    "m6i.large": 70.08, "m7g.large": 59.86,
    "m6i.xlarge": 140.16, "m7g.xlarge": 119.71,
    "m6i.2xlarge": 280.32, "m7g.2xlarge": 239.42,
    "m6i.4xlarge": 560.64, "m7g.4xlarge": 478.85,
    "m6i.8xlarge": 1121.28, "m7g.8xlarge": 957.70,
    "m6i.12xlarge": 1681.92, "m7g.12xlarge": 1436.54,
    "m6i.16xlarge": 2242.56, "m7g.16xlarge": 1915.39,
    "m6i.24xlarge": 3363.84, "m7g.24xlarge": 2873.09,
    "m6i.32xlarge": 4485.12, "m7g.metal": 3564.29,
    # Storage
    "s3_standard_per_gb": 0.023,
    "ebs_gp3_per_gb": 0.08,
    "efs_per_gb": 0.30,
    "glacier_per_gb": 0.004,
    # RDS (db.m6i.large)
    "rds_mysql_per_hour": 0.175,
    "rds_postgres_per_hour": 0.175,
    "rds_oracle_per_hour": 0.475,
    "rds_sqlserver_per_hour": 0.384,
    # Lambda
    "lambda_per_million_requests": 0.20,
    # EKS
    "eks_cluster_per_hour": 0.10,
    # ElastiCache
    "elasticache_redis_per_hour": 0.068,
    # CloudFront
    "cloudfront_per_gb": 0.0085,
}


# ── AWS Calculator URLs (public calculator.aws) ──────────────────────────────

AWS_CALCULATOR_URLS = {
    "AmazonEC2":          "https://calculator.aws/#/createCalculator/ec2-enhancement",
    "AmazonS3":           "https://calculator.aws/#/createCalculator/S3",
    "AmazonEBS":          "https://calculator.aws/#/createCalculator/EBS",
    "AmazonEFS":          "https://calculator.aws/#/createCalculator/EFS",
    "AmazonGlacier":      "https://calculator.aws/#/createCalculator/S3",
    "AmazonRDS":          "https://calculator.aws/#/createCalculator/RDSNew",
    "AmazonDocDB":        "https://calculator.aws/#/createCalculator/DocumentDB",
    "AmazonDynamoDB":     "https://calculator.aws/#/createCalculator/DynamoDB",
    "AmazonElastiCache":  "https://calculator.aws/#/createCalculator/ElastiCache",
    "AmazonKeyspaces":    "https://calculator.aws/#/createCalculator/AmazonMCS",
    "AmazonOpenSearch":   "https://calculator.aws/#/createCalculator/ElasticsearchService",
    "AmazonVPC":          "https://calculator.aws/#/createCalculator/VPC",
    "AmazonCloudFront":   "https://calculator.aws/#/createCalculator/CloudFront",
    "AWSLambda":          "https://calculator.aws/#/createCalculator/Lambda",
    "AmazonEKS":          "https://calculator.aws/#/createCalculator/EKS",
    "AmazonECS":          "https://calculator.aws/#/createCalculator/Fargate",
    "AmazonRedshift":     "https://calculator.aws/#/createCalculator/Redshift",
    "AWSGlue":            "https://calculator.aws/#/createCalculator/Glue",
    "AmazonKinesis":      "https://calculator.aws/#/createCalculator/KinesisDataStreams",
    "AmazonMSK":          "https://calculator.aws/#/createCalculator/MSK",
    "AmazonEMR":          "https://calculator.aws/#/createCalculator/ElasticMapReduce",
    "AWSSecurityHub":     "https://calculator.aws/#/createCalculator/SecurityHub",
    "AWSWAF":             "https://calculator.aws/#/createCalculator/WAF",
    "AWSDirectConnect":   "https://calculator.aws/#/createCalculator/DirectConnect",
    "AWSTransitGateway":  "https://calculator.aws/#/createCalculator/TransitGateway",
    "AmazonRoute53":      "https://calculator.aws/#/createCalculator/Route53",
    "ElasticLoadBalancing":"https://calculator.aws/#/createCalculator/ElasticLoadBalancing",
    "default":            "https://calculator.aws/#/createCalculator",
}


# ── Service-specific pricing models ──────────────────────────────────────────

SERVICE_PRICING_MODELS = {
    "AmazonEC2": ["On-Demand", "Spot", "Reserved 1yr (No Upfront)", "Reserved 1yr (Partial Upfront)",
                  "Reserved 3yr (No Upfront)", "Reserved 3yr (All Upfront)", "Savings Plans", "Graviton (ARM)"],
    "AmazonS3": ["Standard", "Standard-IA", "One Zone-IA", "Intelligent-Tiering", "Glacier Instant Retrieval",
                 "Glacier Flexible Retrieval", "Glacier Deep Archive"],
    "AmazonEBS": ["gp3", "gp2", "io2 Block Express", "io1", "st1 (Throughput Optimized)", "sc1 (Cold HDD)"],
    "AmazonEFS": ["Standard", "Standard-IA", "One Zone", "One Zone-IA"],
    "AmazonRDS": ["On-Demand", "Reserved 1yr (No Upfront)", "Reserved 1yr (All Upfront)",
                  "Reserved 3yr (No Upfront)", "Reserved 3yr (All Upfront)", "Aurora Serverless", "Multi-AZ"],
    "AmazonDocDB": ["On-Demand", "Reserved 1yr", "Reserved 3yr"],
    "AmazonDynamoDB": ["Provisioned", "On-Demand", "Reserved Capacity"],
    "AmazonElastiCache": ["On-Demand", "Reserved 1yr", "Reserved 3yr"],
    "AmazonEKS": ["EC2 Launch Type", "Fargate Launch Type", "Spot Fargate", "Graviton Fargate"],
    "AmazonECS": ["EC2 Launch Type", "Fargate", "Spot Fargate"],
    "AWSLambda": ["Pay-per-invocation", "Provisioned Concurrency"],
    "AmazonRedshift": ["On-Demand", "Reserved 1yr", "Reserved 3yr", "Serverless"],
    "AWSGlue": ["Standard", "Flex", "G.1X", "G.2X"],
    "AmazonCloudFront": ["Pay-per-use", "Security Savings Bundle"],
    "ElasticLoadBalancing": ["Application (ALB)", "Network (NLB)", "Gateway (GWLB)", "Classic (CLB)"],
    "AWSDirectConnect": ["Dedicated Connection", "Hosted Connection"],
    "AWSWAF": ["Pay-per-use"],
    "AWSSecurityHub": ["Pay-per-use"],
}


# ── Service type/SKU options per service ─────────────────────────────────────

SERVICE_TYPE_OPTIONS = {
    "AmazonEC2": [
        "t3.micro", "t3.small", "t3.medium", "t3.large",
        "t4g.micro", "t4g.small", "t4g.medium", "t4g.large",
        "m6i.large", "m6i.xlarge", "m6i.2xlarge", "m6i.4xlarge", "m6i.8xlarge",
        "m7g.large", "m7g.xlarge", "m7g.2xlarge", "m7g.4xlarge", "m7g.8xlarge",
        "c6i.large", "c6i.xlarge", "c6i.2xlarge", "c6i.4xlarge",
        "c7g.large", "c7g.xlarge", "c7g.2xlarge", "c7g.4xlarge",
        "r6i.large", "r6i.xlarge", "r6i.2xlarge", "r6i.4xlarge",
        "r7g.large", "r7g.xlarge", "r7g.2xlarge", "r7g.4xlarge",
    ],
    "AmazonRDS": [
        "db.t3.micro", "db.t3.small", "db.t3.medium", "db.t3.large",
        "db.t4g.micro", "db.t4g.small", "db.t4g.medium", "db.t4g.large",
        "db.m6i.large", "db.m6i.xlarge", "db.m6i.2xlarge", "db.m6i.4xlarge",
        "db.m7g.large", "db.m7g.xlarge", "db.m7g.2xlarge", "db.m7g.4xlarge",
        "db.r6i.large", "db.r6i.xlarge", "db.r6i.2xlarge",
        "db.r7g.large", "db.r7g.xlarge", "db.r7g.2xlarge",
    ],
    "AmazonS3": ["Standard", "Standard-IA", "One Zone-IA", "Intelligent-Tiering",
                 "Glacier Instant Retrieval", "Glacier Flexible Retrieval", "Glacier Deep Archive"],
    "AmazonEBS": ["gp3", "gp2", "io2", "io1", "st1", "sc1"],
    "AmazonEFS": ["Standard", "Standard-IA", "One Zone", "One Zone-IA"],
    "AmazonEKS": ["Managed node group (m7g.large)", "Managed node group (m6i.large)",
                  "Fargate (0.25 vCPU, 0.5 GB)", "Fargate (1 vCPU, 2 GB)", "Fargate (2 vCPU, 4 GB)"],
    "AmazonECS": ["Fargate (0.25 vCPU)", "Fargate (1 vCPU)", "Fargate (2 vCPU)", "EC2 backed"],
    "AWSLambda": ["128 MB", "256 MB", "512 MB", "1024 MB", "2048 MB", "4096 MB", "10240 MB"],
}


# ── SKU Specifications (hardware specs per instance/service type) ─────────────
# Used for comparison: user can see what each SKU provides vs their requirement

SKU_SPECS = {
    # ── EC2 General Purpose (M-family) ────────────────────────────────────────
    "t3.micro":     {"vcpu": 2, "ram_gb": 1, "network_gbps": "Up to 5", "storage": "EBS Only", "arch": "x86_64", "family": "Burstable"},
    "t3.small":     {"vcpu": 2, "ram_gb": 2, "network_gbps": "Up to 5", "storage": "EBS Only", "arch": "x86_64", "family": "Burstable"},
    "t3.medium":    {"vcpu": 2, "ram_gb": 4, "network_gbps": "Up to 5", "storage": "EBS Only", "arch": "x86_64", "family": "Burstable"},
    "t3.large":     {"vcpu": 2, "ram_gb": 8, "network_gbps": "Up to 5", "storage": "EBS Only", "arch": "x86_64", "family": "Burstable"},
    "t4g.micro":    {"vcpu": 2, "ram_gb": 1, "network_gbps": "Up to 5", "storage": "EBS Only", "arch": "arm64 (Graviton2)", "family": "Burstable"},
    "t4g.small":    {"vcpu": 2, "ram_gb": 2, "network_gbps": "Up to 5", "storage": "EBS Only", "arch": "arm64 (Graviton2)", "family": "Burstable"},
    "t4g.medium":   {"vcpu": 2, "ram_gb": 4, "network_gbps": "Up to 5", "storage": "EBS Only", "arch": "arm64 (Graviton2)", "family": "Burstable"},
    "t4g.large":    {"vcpu": 2, "ram_gb": 8, "network_gbps": "Up to 5", "storage": "EBS Only", "arch": "arm64 (Graviton2)", "family": "Burstable"},
    "m6i.large":    {"vcpu": 2, "ram_gb": 8, "network_gbps": "Up to 12.5", "storage": "EBS Only", "arch": "x86_64", "family": "General Purpose"},
    "m6i.xlarge":   {"vcpu": 4, "ram_gb": 16, "network_gbps": "Up to 12.5", "storage": "EBS Only", "arch": "x86_64", "family": "General Purpose"},
    "m6i.2xlarge":  {"vcpu": 8, "ram_gb": 32, "network_gbps": "Up to 12.5", "storage": "EBS Only", "arch": "x86_64", "family": "General Purpose"},
    "m6i.4xlarge":  {"vcpu": 16, "ram_gb": 64, "network_gbps": "Up to 12.5", "storage": "EBS Only", "arch": "x86_64", "family": "General Purpose"},
    "m6i.8xlarge":  {"vcpu": 32, "ram_gb": 128, "network_gbps": 12.5, "storage": "EBS Only", "arch": "x86_64", "family": "General Purpose"},
    "m6i.12xlarge": {"vcpu": 48, "ram_gb": 192, "network_gbps": 18.75, "storage": "EBS Only", "arch": "x86_64", "family": "General Purpose"},
    "m6i.16xlarge": {"vcpu": 64, "ram_gb": 256, "network_gbps": 25, "storage": "EBS Only", "arch": "x86_64", "family": "General Purpose"},
    "m6i.24xlarge": {"vcpu": 96, "ram_gb": 384, "network_gbps": 37.5, "storage": "EBS Only", "arch": "x86_64", "family": "General Purpose"},
    "m6i.32xlarge": {"vcpu": 128, "ram_gb": 512, "network_gbps": 50, "storage": "EBS Only", "arch": "x86_64", "family": "General Purpose"},
    "m7g.large":    {"vcpu": 2, "ram_gb": 8, "network_gbps": "Up to 12.5", "storage": "EBS Only", "arch": "arm64 (Graviton3)", "family": "General Purpose"},
    "m7g.xlarge":   {"vcpu": 4, "ram_gb": 16, "network_gbps": "Up to 12.5", "storage": "EBS Only", "arch": "arm64 (Graviton3)", "family": "General Purpose"},
    "m7g.2xlarge":  {"vcpu": 8, "ram_gb": 32, "network_gbps": "Up to 15", "storage": "EBS Only", "arch": "arm64 (Graviton3)", "family": "General Purpose"},
    "m7g.4xlarge":  {"vcpu": 16, "ram_gb": 64, "network_gbps": "Up to 15", "storage": "EBS Only", "arch": "arm64 (Graviton3)", "family": "General Purpose"},
    "m7g.8xlarge":  {"vcpu": 32, "ram_gb": 128, "network_gbps": 15, "storage": "EBS Only", "arch": "arm64 (Graviton3)", "family": "General Purpose"},
    "m7g.12xlarge": {"vcpu": 48, "ram_gb": 192, "network_gbps": 22.5, "storage": "EBS Only", "arch": "arm64 (Graviton3)", "family": "General Purpose"},
    "m7g.16xlarge": {"vcpu": 64, "ram_gb": 256, "network_gbps": 30, "storage": "EBS Only", "arch": "arm64 (Graviton3)", "family": "General Purpose"},
    "m7g.metal":    {"vcpu": 64, "ram_gb": 256, "network_gbps": 30, "storage": "EBS Only", "arch": "arm64 (Graviton3)", "family": "General Purpose"},
    # ── EC2 Compute Optimized (C-family) ──────────────────────────────────────
    "c6i.large":    {"vcpu": 2, "ram_gb": 4, "network_gbps": "Up to 12.5", "storage": "EBS Only", "arch": "x86_64", "family": "Compute Optimized"},
    "c6i.xlarge":   {"vcpu": 4, "ram_gb": 8, "network_gbps": "Up to 12.5", "storage": "EBS Only", "arch": "x86_64", "family": "Compute Optimized"},
    "c6i.2xlarge":  {"vcpu": 8, "ram_gb": 16, "network_gbps": "Up to 12.5", "storage": "EBS Only", "arch": "x86_64", "family": "Compute Optimized"},
    "c6i.4xlarge":  {"vcpu": 16, "ram_gb": 32, "network_gbps": "Up to 12.5", "storage": "EBS Only", "arch": "x86_64", "family": "Compute Optimized"},
    "c7g.large":    {"vcpu": 2, "ram_gb": 4, "network_gbps": "Up to 12.5", "storage": "EBS Only", "arch": "arm64 (Graviton3)", "family": "Compute Optimized"},
    "c7g.xlarge":   {"vcpu": 4, "ram_gb": 8, "network_gbps": "Up to 12.5", "storage": "EBS Only", "arch": "arm64 (Graviton3)", "family": "Compute Optimized"},
    "c7g.2xlarge":  {"vcpu": 8, "ram_gb": 16, "network_gbps": "Up to 15", "storage": "EBS Only", "arch": "arm64 (Graviton3)", "family": "Compute Optimized"},
    "c7g.4xlarge":  {"vcpu": 16, "ram_gb": 32, "network_gbps": "Up to 15", "storage": "EBS Only", "arch": "arm64 (Graviton3)", "family": "Compute Optimized"},
    # ── EC2 Memory Optimized (R-family) ───────────────────────────────────────
    "r6i.large":    {"vcpu": 2, "ram_gb": 16, "network_gbps": "Up to 12.5", "storage": "EBS Only", "arch": "x86_64", "family": "Memory Optimized"},
    "r6i.xlarge":   {"vcpu": 4, "ram_gb": 32, "network_gbps": "Up to 12.5", "storage": "EBS Only", "arch": "x86_64", "family": "Memory Optimized"},
    "r6i.2xlarge":  {"vcpu": 8, "ram_gb": 64, "network_gbps": "Up to 12.5", "storage": "EBS Only", "arch": "x86_64", "family": "Memory Optimized"},
    "r6i.4xlarge":  {"vcpu": 16, "ram_gb": 128, "network_gbps": "Up to 12.5", "storage": "EBS Only", "arch": "x86_64", "family": "Memory Optimized"},
    "r7g.large":    {"vcpu": 2, "ram_gb": 16, "network_gbps": "Up to 12.5", "storage": "EBS Only", "arch": "arm64 (Graviton3)", "family": "Memory Optimized"},
    "r7g.xlarge":   {"vcpu": 4, "ram_gb": 32, "network_gbps": "Up to 12.5", "storage": "EBS Only", "arch": "arm64 (Graviton3)", "family": "Memory Optimized"},
    "r7g.2xlarge":  {"vcpu": 8, "ram_gb": 64, "network_gbps": "Up to 15", "storage": "EBS Only", "arch": "arm64 (Graviton3)", "family": "Memory Optimized"},
    "r7g.4xlarge":  {"vcpu": 16, "ram_gb": 128, "network_gbps": "Up to 15", "storage": "EBS Only", "arch": "arm64 (Graviton3)", "family": "Memory Optimized"},
    # ── EC2 GPU instances ─────────────────────────────────────────────────────
    "p4d.24xlarge": {"vcpu": 96, "ram_gb": 1152, "network_gbps": 400, "storage": "8x 1000 GB NVMe SSD", "arch": "x86_64", "family": "GPU (A100)", "gpu": "8x NVIDIA A100 40GB"},
    "p3.2xlarge":   {"vcpu": 8, "ram_gb": 61, "network_gbps": "Up to 10", "storage": "EBS Only", "arch": "x86_64", "family": "GPU (V100)", "gpu": "1x NVIDIA V100 16GB"},
    "g4dn.xlarge":  {"vcpu": 4, "ram_gb": 16, "network_gbps": "Up to 25", "storage": "125 GB NVMe SSD", "arch": "x86_64", "family": "GPU (T4)", "gpu": "1x NVIDIA T4 16GB"},
    "g5.xlarge":    {"vcpu": 4, "ram_gb": 16, "network_gbps": "Up to 10", "storage": "250 GB NVMe SSD", "arch": "x86_64", "family": "GPU (A10G)", "gpu": "1x NVIDIA A10G 24GB"},
    "inf2.xlarge":  {"vcpu": 4, "ram_gb": 16, "network_gbps": "Up to 15", "storage": "EBS Only", "arch": "x86_64", "family": "ML Inference (Inferentia2)", "gpu": "1x AWS Inferentia2"},
    # ── RDS instances ─────────────────────────────────────────────────────────
    "db.t3.micro":   {"vcpu": 2, "ram_gb": 1, "network_gbps": "Low to Moderate", "storage": "Up to 16 TB", "arch": "x86_64", "family": "Burstable"},
    "db.t3.small":   {"vcpu": 2, "ram_gb": 2, "network_gbps": "Low to Moderate", "storage": "Up to 16 TB", "arch": "x86_64", "family": "Burstable"},
    "db.t3.medium":  {"vcpu": 2, "ram_gb": 4, "network_gbps": "Low to Moderate", "storage": "Up to 16 TB", "arch": "x86_64", "family": "Burstable"},
    "db.t3.large":   {"vcpu": 2, "ram_gb": 8, "network_gbps": "Low to Moderate", "storage": "Up to 16 TB", "arch": "x86_64", "family": "Burstable"},
    "db.t4g.micro":  {"vcpu": 2, "ram_gb": 1, "network_gbps": "Low to Moderate", "storage": "Up to 16 TB", "arch": "arm64 (Graviton2)", "family": "Burstable"},
    "db.t4g.small":  {"vcpu": 2, "ram_gb": 2, "network_gbps": "Low to Moderate", "storage": "Up to 16 TB", "arch": "arm64 (Graviton2)", "family": "Burstable"},
    "db.t4g.medium": {"vcpu": 2, "ram_gb": 4, "network_gbps": "Low to Moderate", "storage": "Up to 16 TB", "arch": "arm64 (Graviton2)", "family": "Burstable"},
    "db.t4g.large":  {"vcpu": 2, "ram_gb": 8, "network_gbps": "Low to Moderate", "storage": "Up to 16 TB", "arch": "arm64 (Graviton2)", "family": "Burstable"},
    "db.m6i.large":  {"vcpu": 2, "ram_gb": 8, "network_gbps": "Up to 12.5", "storage": "Up to 64 TB", "arch": "x86_64", "family": "General Purpose"},
    "db.m6i.xlarge": {"vcpu": 4, "ram_gb": 16, "network_gbps": "Up to 12.5", "storage": "Up to 64 TB", "arch": "x86_64", "family": "General Purpose"},
    "db.m6i.2xlarge":{"vcpu": 8, "ram_gb": 32, "network_gbps": "Up to 12.5", "storage": "Up to 64 TB", "arch": "x86_64", "family": "General Purpose"},
    "db.m6i.4xlarge":{"vcpu": 16, "ram_gb": 64, "network_gbps": "Up to 12.5", "storage": "Up to 64 TB", "arch": "x86_64", "family": "General Purpose"},
    "db.m7g.large":  {"vcpu": 2, "ram_gb": 8, "network_gbps": "Up to 12.5", "storage": "Up to 64 TB", "arch": "arm64 (Graviton3)", "family": "General Purpose"},
    "db.m7g.xlarge": {"vcpu": 4, "ram_gb": 16, "network_gbps": "Up to 12.5", "storage": "Up to 64 TB", "arch": "arm64 (Graviton3)", "family": "General Purpose"},
    "db.m7g.2xlarge":{"vcpu": 8, "ram_gb": 32, "network_gbps": "Up to 15", "storage": "Up to 64 TB", "arch": "arm64 (Graviton3)", "family": "General Purpose"},
    "db.m7g.4xlarge":{"vcpu": 16, "ram_gb": 64, "network_gbps": "Up to 15", "storage": "Up to 64 TB", "arch": "arm64 (Graviton3)", "family": "General Purpose"},
    "db.r6i.large":  {"vcpu": 2, "ram_gb": 16, "network_gbps": "Up to 12.5", "storage": "Up to 64 TB", "arch": "x86_64", "family": "Memory Optimized"},
    "db.r6i.xlarge": {"vcpu": 4, "ram_gb": 32, "network_gbps": "Up to 12.5", "storage": "Up to 64 TB", "arch": "x86_64", "family": "Memory Optimized"},
    "db.r6i.2xlarge":{"vcpu": 8, "ram_gb": 64, "network_gbps": "Up to 12.5", "storage": "Up to 64 TB", "arch": "x86_64", "family": "Memory Optimized"},
    "db.r7g.large":  {"vcpu": 2, "ram_gb": 16, "network_gbps": "Up to 12.5", "storage": "Up to 64 TB", "arch": "arm64 (Graviton3)", "family": "Memory Optimized"},
    "db.r7g.xlarge": {"vcpu": 4, "ram_gb": 32, "network_gbps": "Up to 12.5", "storage": "Up to 64 TB", "arch": "arm64 (Graviton3)", "family": "Memory Optimized"},
    "db.r7g.2xlarge":{"vcpu": 8, "ram_gb": 64, "network_gbps": "Up to 15", "storage": "Up to 64 TB", "arch": "arm64 (Graviton3)", "family": "Memory Optimized"},
    # ── EBS volumes ───────────────────────────────────────────────────────────
    "gp3":  {"iops": "3,000 (up to 16,000)", "throughput_mbps": "125 (up to 1,000)", "max_size_tb": 16, "type": "SSD", "use_case": "General purpose, balanced price/performance"},
    "gp2":  {"iops": "100–16,000 (burst)", "throughput_mbps": "Up to 250", "max_size_tb": 16, "type": "SSD", "use_case": "Previous gen general purpose"},
    "io2":  {"iops": "Up to 256,000", "throughput_mbps": "Up to 4,000", "max_size_tb": 64, "type": "SSD (Provisioned IOPS)", "use_case": "Mission-critical, sustained IOPS"},
    "io1":  {"iops": "Up to 64,000", "throughput_mbps": "Up to 1,000", "max_size_tb": 16, "type": "SSD (Provisioned IOPS)", "use_case": "High-performance databases"},
    "st1":  {"iops": "Up to 500", "throughput_mbps": "Up to 500", "max_size_tb": 16, "type": "HDD (Throughput)", "use_case": "Big data, data warehouses, log processing"},
    "sc1":  {"iops": "Up to 250", "throughput_mbps": "Up to 250", "max_size_tb": 16, "type": "HDD (Cold)", "use_case": "Infrequent access, lowest cost"},
    # ── S3 tiers ──────────────────────────────────────────────────────────────
    "Standard":                 {"durability": "99.999999999%", "availability": "99.99%", "retrieval": "Instant", "min_storage_days": 0, "use_case": "Frequently accessed data"},
    "Standard-IA":              {"durability": "99.999999999%", "availability": "99.9%", "retrieval": "Instant", "min_storage_days": 30, "use_case": "Infrequent access, rapid retrieval"},
    "One Zone-IA":              {"durability": "99.999999999%", "availability": "99.5%", "retrieval": "Instant", "min_storage_days": 30, "use_case": "Re-creatable infrequent data"},
    "Intelligent-Tiering":      {"durability": "99.999999999%", "availability": "99.9%", "retrieval": "Instant", "min_storage_days": 0, "use_case": "Auto-tiering, unknown access patterns"},
    "Glacier Instant Retrieval":{"durability": "99.999999999%", "availability": "99.9%", "retrieval": "Milliseconds", "min_storage_days": 90, "use_case": "Long-lived archive, instant access"},
    "Glacier Flexible Retrieval":{"durability": "99.999999999%", "availability": "99.99%", "retrieval": "1-12 hours", "min_storage_days": 90, "use_case": "Archive, flexible retrieval"},
    "Glacier Deep Archive":     {"durability": "99.999999999%", "availability": "99.99%", "retrieval": "12-48 hours", "min_storage_days": 180, "use_case": "Lowest cost long-term archive"},
    # ── Lambda memory configs ─────────────────────────────────────────────────
    "128 MB":   {"ram_mb": 128, "vcpu_share": "~0.08 vCPU", "max_timeout_sec": 900, "use_case": "Simple triggers, lightweight APIs"},
    "256 MB":   {"ram_mb": 256, "vcpu_share": "~0.17 vCPU", "max_timeout_sec": 900, "use_case": "Small API handlers"},
    "512 MB":   {"ram_mb": 512, "vcpu_share": "~0.33 vCPU", "max_timeout_sec": 900, "use_case": "Medium processing tasks"},
    "1024 MB":  {"ram_mb": 1024, "vcpu_share": "~0.58 vCPU", "max_timeout_sec": 900, "use_case": "Data transformation, image processing"},
    "2048 MB":  {"ram_mb": 2048, "vcpu_share": "~1.17 vCPU", "max_timeout_sec": 900, "use_case": "ML inference, heavy computation"},
    "4096 MB":  {"ram_mb": 4096, "vcpu_share": "~2.33 vCPU", "max_timeout_sec": 900, "use_case": "Large data processing"},
    "10240 MB": {"ram_mb": 10240, "vcpu_share": "6 vCPU", "max_timeout_sec": 900, "use_case": "Maximum compute Lambda workloads"},
    # ── EFS tiers ─────────────────────────────────────────────────────────────
    "EFS Standard":    {"throughput": "Elastic (auto-scales)", "availability": "Multi-AZ", "latency": "Sub-millisecond", "use_case": "Shared file system, frequently accessed"},
    "EFS Standard-IA": {"throughput": "Elastic", "availability": "Multi-AZ", "latency": "Single-digit ms", "use_case": "Infrequent access, lifecycle policy"},
    "EFS One Zone":    {"throughput": "Elastic", "availability": "Single-AZ", "latency": "Sub-millisecond", "use_case": "Dev/test, single-AZ workloads"},
    "EFS One Zone-IA": {"throughput": "Elastic", "availability": "Single-AZ", "latency": "Single-digit ms", "use_case": "Infrequent, single-AZ"},
}


def get_sku_specs(sku: str) -> dict:
    """Return hardware specs for a given SKU. Returns empty dict if not found."""
    return SKU_SPECS.get(sku, {})


def get_all_sku_specs() -> dict:
    """Return the full SKU specs dictionary."""
    return SKU_SPECS


# ── Region service availability (limited services per region) ─────────────────

# Regions where certain services are NOT available
# Most services are available in all regions; only list exceptions
REGION_SERVICE_EXCLUSIONS = {
    "af-south-1": ["AmazonRedshift Serverless", "AmazonMSK", "AWSGlue Flex"],
    "ap-east-1": ["AmazonRedshift Serverless"],
    "ap-southeast-3": ["AmazonRedshift", "AmazonMSK", "AmazonEMR", "AWSGlue"],
    "eu-south-1": ["AmazonRedshift Serverless"],
    "eu-south-2": ["AmazonRedshift", "AmazonMSK", "AmazonEMR"],
    "eu-central-2": ["AmazonRedshift", "AmazonMSK", "AmazonEMR"],
    "me-south-1": ["AmazonRedshift Serverless", "AmazonMSK"],
    "me-central-1": ["AmazonRedshift", "AmazonMSK", "AmazonEMR"],
    "il-central-1": ["AmazonMSK", "AmazonEMR"],
    "ca-west-1": ["AmazonRedshift", "AmazonMSK", "AmazonEMR", "AmazonOpenSearch"],
    "ap-south-2": ["AmazonRedshift", "AmazonMSK", "AmazonEMR"],
    "ap-southeast-4": ["AmazonRedshift", "AmazonMSK", "AmazonEMR"],
}

# Graviton instances availability — most regions have them, only list those that don't
GRAVITON_UNAVAILABLE_REGIONS = [
    "ap-southeast-3",  # Jakarta (limited Graviton)
    "eu-south-2",      # Spain (limited Graviton)
    "me-central-1",    # UAE (limited Graviton)
]


def get_calculator_url(service_code: str) -> str:
    """Return the correct public AWS Pricing Calculator URL for a service."""
    return AWS_CALCULATOR_URLS.get(service_code, AWS_CALCULATOR_URLS["default"])


def get_pricing_models(service_code: str) -> List[str]:
    """Return applicable pricing models for a given service."""
    return SERVICE_PRICING_MODELS.get(service_code, ["On-Demand", "Pay-per-use"])


def get_service_types(service_code: str) -> List[str]:
    """Return available SKU/type options for a given service."""
    return SERVICE_TYPE_OPTIONS.get(service_code, [])


def is_service_available(service_code: str, region: str) -> bool:
    """Check if a service is available in the specified region."""
    exclusions = REGION_SERVICE_EXCLUSIONS.get(region, [])
    return service_code not in exclusions


def is_graviton_available(region: str) -> bool:
    """Check if Graviton instances are available in the specified region."""
    return region not in GRAVITON_UNAVAILABLE_REGIONS


# ── Keyword extraction patterns ───────────────────────────────────────────────

COMPUTE_PATTERNS = [
    r"(\d+)\s*(?:x\s*)?(?:vcpu|vcore|core|cpu|processor|thread)s?",
    r"(\d+)\s*(?:x\s*)?(?:physical\s+)?server",
    r"(\d+)\s*(?:x\s*)?(?:vm|virtual machine|instance|node)s?",
    r"(\d+)\s*(?:x\s*)?(?:worker|master|control.plane)\s*node",
    r"ram[:\s]+(\d+(?:\.\d+)?)\s*(gb|tb|mb)",
    r"memory[:\s]+(\d+(?:\.\d+)?)\s*(gb|tb|mb)",
    r"(\d+(?:\.\d+)?)\s*(gb|tb)\s+(?:of\s+)?(?:ram|memory)",
    r"(\d+(?:\.\d+)?)\s*gb\s+ram",
]

STORAGE_PATTERNS = [
    r"(\d+(?:\.\d+)?)\s*(tb|gb|pb)\s+(?:of\s+)?(?:storage|disk|hdd|ssd|nvme|capacity)",
    r"(?:storage|disk|capacity)[:\s]+(\d+(?:\.\d+)?)\s*(tb|gb|pb)",
    r"(\d+(?:\.\d+)?)\s*(tb|gb)\s+(?:object\s+)?storage",
    r"(\d+(?:\.\d+)?)\s*(tb|gb)\s+(?:block\s+)?storage",
    r"(\d+)\s*iops",
    r"iops[:\s]+(\d+)",
    r"throughput[:\s]+(\d+(?:\.\d+)?)\s*(mb/s|gb/s|mbps|gbps)",
]

NETWORK_PATTERNS = [
    r"(\d+(?:\.\d+)?)\s*(gbps|mbps|gb/s|mb/s)\s+(?:network|bandwidth|throughput|uplink)",
    r"(?:bandwidth|throughput)[:\s]+(\d+(?:\.\d+)?)\s*(gbps|mbps|gb/s|mb/s)",
    r"(\d+(?:\.\d+)?)\s*(tbps|gbps)\s+(?:internet|egress|ingress)",
    r"(\d+)\s+(?:network\s+)?(?:interface|nic|port)",
]

DATABASE_PATTERNS = [
    r"(?:database|db)[:\s]*(?:type|engine)?[:\s]*(postgresql|postgres|mysql|mariadb|oracle|sql server|mssql|mongodb|redis|cassandra|elasticsearch|dynamodb)",
    r"(postgresql|postgres|mysql|mariadb|oracle|sql server|mssql|mongodb|redis|cassandra|elasticsearch)\s+(?:database|db|server|cluster)",
    r"(\d+(?:\.\d+)?)\s*(gb|tb)\s+(?:database|db)\s+(?:storage|size|capacity)",
]

GPU_PATTERNS = [
    r"(\d+)\s*(?:x\s*)?gpu",
    r"gpu[:\s]+(\d+)",
    r"(?:nvidia|amd|intel)\s+(?:a100|h100|v100|t4|a10|a40|l40|rtx\s*\d+|tesla)",
    r"machine learning|deep learning|ai inference|training workload",
]


def _deep_scan_sections(text: str) -> List[str]:
    """
    Split long documents into overlapping chunks for extraction.
    If total text <= 50,000 chars, return as a single chunk.
    Otherwise, chunk into 10,000-char windows with 500-char overlap.
    Section headings are used to prioritize but all text is scanned.
    """
    if len(text) <= 50000:
        return [text]

    chunks = []
    chunk_size = 10000
    overlap = 500
    pos = 0
    while pos < len(text):
        end = min(pos + chunk_size, len(text))
        chunks.append(text[pos:end])
        pos += chunk_size - overlap
    return chunks


def analyze_spec(text: str, region: str = "us-east-1", extra_context: dict = None) -> dict:
    """
    Main entry point. Takes raw spec text and returns structured analysis.

    Args:
        text:          Raw spec text (potentially multi-page / multi-section)
        region:        AWS region code for pricing (default: us-east-1)
        extra_context: Dict of {missing_field_label: user_provided_value} to
                       supplement the spec with answers to previously flagged
                       missing info items.
    """
    # If the user filled in missing info, append it to the text
    if extra_context:
        supplements = "\n\n=== SUPPLEMENTAL INFORMATION PROVIDED BY USER ===\n"
        for key, val in extra_context.items():
            if val and str(val).strip():
                supplements += f"{key}: {val}\n"
        text = text + supplements

    # Normalize and deep-scan multi-section documents
    text = _normalize_text(text)
    text_lower = text.lower()

    source_platform = _detect_platform(text_lower)
    translated_text = _translate_vendor_terms(text_lower)

    # Deep-scan: chunk into overlapping windows for extraction
    chunks = _deep_scan_sections(text)
    translated_chunks = _deep_scan_sections(translated_text)

    # Extract requirements from each chunk, then merge
    all_requirements = []
    for i, chunk in enumerate(chunks):
        t_chunk = translated_chunks[i] if i < len(translated_chunks) else translated_text
        chunk_reqs = _extract_requirements(chunk, t_chunk, source_platform)
        all_requirements.extend(chunk_reqs)

    # Merge chunk-level requirements: deduplicate by category, take max values
    requirements = _merge_chunk_requirements(all_requirements, source_platform)

    mappings = [_map_requirement(req, region) for req in requirements]

    # Overall confidence
    confidence_scores = [m.confidence for m in mappings]
    if not mappings:
        overall_confidence = "needs_info"
    elif all(c == "high" for c in confidence_scores):
        overall_confidence = "high"
    elif "needs_info" in confidence_scores or \
         len([c for c in confidence_scores if c in ("low", "needs_info")]) > len(mappings) / 2:
        overall_confidence = "needs_info"
    elif "low" in confidence_scores:
        overall_confidence = "medium"
    else:
        overall_confidence = "medium"

    all_missing = []
    for m in mappings:
        all_missing.extend(m.missing_info)
    all_missing = list(dict.fromkeys(all_missing))

    total_monthly = sum(m.monthly_estimate_usd for m in mappings)
    region_label  = REGION_LABELS.get(region, region)

    return {
        "source_platform":           source_platform,
        "overall_confidence":        overall_confidence,
        "missing_info":              all_missing,
        "mappings":                  [_mapping_to_dict(m) for m in mappings],
        "total_monthly_estimate_usd": round(total_monthly, 2),
        "region":                    region,
        "region_label":              region_label,
        "all_regions":               [(c, l, mult) for c, l, mult in all_regions()],
        "aws_calculator_base_url":   "https://calculator.aws/pricing/2/home",
        "summary":                   _build_summary(source_platform, mappings, overall_confidence),
    }


def _merge_chunk_requirements(all_reqs: List[SpecRequirement], platform: str) -> List[SpecRequirement]:
    """
    Merge requirements extracted from multiple chunks.
    For numeric metrics (vCPU, RAM, storage, bandwidth, GPU count), take the max.
    For categorical detections (DB engines, keyword-based categories), union.
    """
    # Group by category
    by_category = {}
    for req in all_reqs:
        cat = req.category
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(req)

    merged = []

    for cat, reqs in by_category.items():
        if cat == "Compute":
            # Take max vCPU, max RAM, max instance count
            best = reqs[0]
            max_vcpu = max((getattr(r, "_vcpu", 0) for r in reqs), default=0)
            max_ram = max((getattr(r, "_ram_gb", 0) for r in reqs), default=0)
            max_qty = max((r.quantity for r in reqs), default=1)
            best._vcpu = max_vcpu
            best._ram_gb = max_ram
            best.quantity = max_qty
            best.notes = f"vCPU: {max_vcpu or 'unspecified'}, RAM: {max_ram or 'unspecified'} GB"
            merged.append(best)

        elif cat == "Storage":
            best = reqs[0]
            max_tb = max((getattr(r, "_storage_tb", 0) for r in reqs), default=0)
            max_iops = max((getattr(r, "_iops", 0) for r in reqs), default=0)
            # Use the most specific storage type
            storage_types = [getattr(r, "_storage_type", "general") for r in reqs]
            specific_types = [t for t in storage_types if t != "general"]
            best._storage_type = specific_types[0] if specific_types else "general"
            best._storage_tb = max_tb
            best._iops = max_iops
            best.value = max_tb * 1024 if max_tb else 0
            best.notes = f"Type: {best._storage_type}, Size: {max_tb or 'unspecified'} TB, IOPS: {max_iops or 'unspecified'}"
            merged.append(best)

        elif cat == "Database":
            # Union of distinct engines
            seen_engines = set()
            for req in reqs:
                engine = getattr(req, "_db_engine", "unspecified")
                if engine not in seen_engines:
                    seen_engines.add(engine)
                    merged.append(req)

        elif cat == "Networking":
            best = reqs[0]
            max_bw = max((getattr(r, "_bandwidth_gbps", 0) for r in reqs), default=0)
            best._bandwidth_gbps = max_bw
            best.notes = f"Bandwidth: {max_bw or 'unspecified'} Gbps"
            # Use the longest raw_description for best context
            best.raw_description = max((r.raw_description for r in reqs), key=len)
            merged.append(best)

        elif cat == "GPU/ML":
            best = reqs[0]
            max_gpu = max((getattr(r, "_gpu_count", 0) for r in reqs), default=0)
            # Take any detected model
            models = [getattr(r, "_gpu_model", "") for r in reqs]
            best_model = next((m for m in models if m), "")
            best._gpu_count = max_gpu
            best._gpu_model = best_model
            best.quantity = max(max_gpu, 1)
            best.notes = f"GPU Count: {max_gpu or 'unspecified'}, Model: {best_model or 'unspecified'}"
            merged.append(best)

        elif cat == "Unknown":
            # Only include if nothing else was found
            if len(by_category) == 1:
                merged.append(reqs[0])

        else:
            # Containers, Serverless/API, Analytics/Data, Security/Identity
            # Just keep one (they're keyword-triggered, not numeric)
            merged.append(reqs[0])

    # If we have real categories but also got Unknown, drop Unknown
    if len(merged) > 1:
        merged = [r for r in merged if r.category != "Unknown"]

    return merged


def _normalize_text(text: str) -> str:
    """
    Normalize a long / multi-section document for better extraction.
    - Collapse excessive whitespace
    - Preserve section headers (lines with all-caps or ending with colon)
    - Extract tables into flat key:value lines
    """
    lines = text.split("\n")
    normalized = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Collapse runs of whitespace inside a line
        stripped = re.sub(r'[ \t]{2,}', ' ', stripped)
        normalized.append(stripped)
    return "\n".join(normalized)


def _detect_platform(text: str) -> str:
    azure_keywords = ["azure", "microsoft azure", "expressroute", "cosmos db", "aks", "vnet", "azure devops"]
    gcp_keywords = ["gcp", "google cloud", "gce", "gke", "bigquery", "cloud run", "vertex ai", "pubsub", "pub/sub"]
    onprem_keywords = ["on-prem", "on prem", "on-premises", "on premises", "data center", "datacenter",
                       "bare metal", "physical server", "rack", "blade", "san ", "nas ", "vmware", "hyper-v"]

    az_count = sum(1 for kw in azure_keywords if kw in text)
    gcp_count = sum(1 for kw in gcp_keywords if kw in text)
    op_count = sum(1 for kw in onprem_keywords if kw in text)

    if az_count > gcp_count and az_count > op_count:
        return "azure"
    elif gcp_count > az_count and gcp_count > op_count:
        return "gcp"
    elif op_count > 0:
        return "onprem"
    else:
        return "generic"


def _translate_vendor_terms(text: str) -> str:
    """Replace vendor-specific terms with normalized labels for easier pattern matching."""
    result = text
    # Combine all translation dicts
    all_translations = {}
    all_translations.update(AZURE_TO_AWS)
    all_translations.update(GCP_TO_AWS)
    all_translations.update(ONPREM_TO_AWS)

    for vendor_term, aws_term in sorted(all_translations.items(), key=lambda x: -len(x[0])):
        result = result.replace(vendor_term, f"[AWS:{aws_term}]")
    return result


def _is_it_infrastructure_context(text_lower: str) -> bool:
    """
    Validate that the text is actually about IT/computing infrastructure,
    not about irrigation, water storage, civil engineering, etc.
    Returns True if the text appears to be about IT infrastructure.
    """
    # Strong IT indicators — if these appear, it's likely an IT spec
    strong_it_signals = ["cpu", "vcpu", "ram", "server", "virtual machine", "database",
                         "operating system", "linux", "windows server", "ubuntu",
                         "ip address", "ipv4", "ipv6", "bandwidth", "mbps", "gbps",
                         "disk space", "ssd", "hdd", "nvme", "iops",
                         "cloud", "aws", "azure", "gcp", "vmware", "docker",
                         "postgresql", "mysql", "mongodb", "redis", "sql server",
                         "api", "http", "https", "ssl", "dns", "firewall"]
    
    # Non-IT signals — documents about civil engineering, agriculture, etc.
    non_it_signals = ["irrigation", "flood control", "drainage", "water supply",
                      "sanitation", "sewerage", "solid waste", "civil engineering",
                      "construction", "bridge", "road", "building permit",
                      "agricultural", "farming", "livestock", "harvest"]
    
    it_score = sum(1 for kw in strong_it_signals if kw in text_lower)
    non_it_score = sum(1 for kw in non_it_signals if kw in text_lower)
    
    # If more non-IT signals than IT signals, this isn't an IT infrastructure spec
    if non_it_score > it_score and it_score < 3:
        return False
    return it_score >= 2


def _extract_requirements(original_text: str, translated_text: str, platform: str) -> List[SpecRequirement]:
    """
    Intelligently extract infrastructure requirements from spec text.
    
    Key principles:
    - Only create separate service categories when the spec EXPLICITLY requires them
    - Disk space attached to a server is NOT a separate storage requirement
    - Basic network connectivity (IPs, bandwidth < 100 Mbps) is NOT a separate networking service
    - Keywords like "docker" or "container" in a description don't mean container orchestration is needed
    - GPU mentioned in passing doesn't mean GPU instances are needed
    - Detect SaaS/application patterns that don't map to raw AWS infrastructure
    - Validate that detected keywords are in an IT context (not civil engineering, agriculture, etc.)
    """
    requirements = []
    text_lower = original_text.lower()

    # ── Context validation ────────────────────────────────────────────────────
    # Check if this text is actually about IT infrastructure
    is_it_context = _is_it_infrastructure_context(text_lower)
    
    if not is_it_context:
        # Document doesn't appear to be about IT infrastructure
        req = SpecRequirement(
            category="Unknown",
            raw_description=original_text[:500],
            source_platform=platform,
            notes="This document does not appear to contain IT infrastructure specifications. "
                  "It may be about civil engineering, agriculture, or another non-IT domain. "
                  "If there is an IT section, try uploading only the relevant pages."
        )
        return [req]

    # ── SaaS / Application Detection ─────────────────────────────────────────
    # If the spec describes a SaaS product/application (not infrastructure), flag it
    saas_indicators = ["saas", "software as a service", "subscription", "per user", "per seat",
                       "monthly subscription", "annual license", "cloud-hosted application",
                       "managed service", "fully managed"]
    saas_score = sum(1 for kw in saas_indicators if kw in text_lower)
    
    # If spec is primarily about a SaaS product, add a note but still try to extract infra
    is_saas_spec = saas_score >= 2

    # ── Compute ───────────────────────────────────────────────────────────────
    vcpu_count = 0
    ram_gb = 0
    instance_count = 1

    for pattern in COMPUTE_PATTERNS:
        matches = re.findall(pattern, text_lower)
        for m in matches:
            if isinstance(m, tuple):
                val, unit = m[0], (m[1] if len(m) > 1 else "")
            else:
                val, unit = m, ""
            try:
                num = float(val)
                if "vcpu" in pattern or "core" in pattern or "cpu" in pattern or "thread" in pattern:
                    vcpu_count = max(vcpu_count, int(num))
                elif "server" in pattern or "vm" in pattern or "instance" in pattern or "node" in pattern:
                    instance_count = max(instance_count, int(num))
                elif "ram" in pattern or "memory" in pattern:
                    unit_lower = unit.lower() if unit else ""
                    if unit_lower == "tb":
                        ram_gb = max(ram_gb, num * 1024)
                    elif unit_lower == "mb":
                        ram_gb = max(ram_gb, num / 1024)
                    else:
                        ram_gb = max(ram_gb, num)
            except (ValueError, IndexError):
                pass

    has_compute = vcpu_count > 0 or ram_gb > 0 or instance_count > 1
    if has_compute:
        req = SpecRequirement(
            category="Compute",
            raw_description=_extract_context(original_text, ["server", "compute", "cpu", "vcpu", "instance", "vm", "node"]),
            quantity=max(instance_count, 1),
            unit="instance",
            value=vcpu_count,
            source_platform=platform,
            notes=f"vCPU: {vcpu_count or 'unspecified'}, RAM: {ram_gb or 'unspecified'} GB"
        )
        req._vcpu = vcpu_count
        req._ram_gb = ram_gb
        requirements.append(req)

    # ── Storage ───────────────────────────────────────────────────────────────
    # ONLY create a separate storage requirement if the spec explicitly asks for
    # standalone/shared/external storage (NAS, SAN, S3, object storage, etc.)
    # Local disk space on a server does NOT count as a separate storage service.
    storage_tb = 0
    iops = 0
    storage_type = "general"
    is_standalone_storage = False

    for pattern in STORAGE_PATTERNS:
        matches = re.findall(pattern, text_lower)
        for m in matches:
            if isinstance(m, tuple) and len(m) >= 2:
                val, unit = m[0], m[1]
                try:
                    num = float(val)
                    if "iops" in pattern:
                        iops = max(iops, int(num))
                    elif unit.lower() == "tb" or unit.lower() == "pb":
                        mult = 1 if unit.lower() == "tb" else 1024
                        storage_tb = max(storage_tb, num * mult)
                    elif unit.lower() == "gb":
                        storage_tb = max(storage_tb, num / 1024)
                except (ValueError, IndexError):
                    pass

    # Determine if storage is standalone (separate service) or just local disk
    standalone_storage_keywords = ["object storage", "blob", "s3", "nas", "nfs", "san",
                                   "shared storage", "file share", "backup storage",
                                   "archive", "glacier", "data lake", "efs", "fsx"]
    local_disk_keywords = ["disk space", "disk:", "local disk", "root volume", "boot disk"]

    if any(kw in text_lower for kw in standalone_storage_keywords):
        is_standalone_storage = True
    elif storage_tb > 5:  # More than 5 TB suggests dedicated storage
        is_standalone_storage = True
    elif iops > 10000:  # High IOPS suggests dedicated storage
        is_standalone_storage = True

    if "object storage" in text_lower or "blob" in text_lower or "s3" in text_lower:
        storage_type = "object"
    elif "block storage" in text_lower or "san" in text_lower or "ebs" in text_lower:
        storage_type = "block"
    elif "file storage" in text_lower or "nas" in text_lower or "nfs" in text_lower or "efs" in text_lower:
        storage_type = "file"
    elif "archive" in text_lower or "backup" in text_lower or "glacier" in text_lower or "tape" in text_lower:
        storage_type = "archive"

    # Only add storage as a separate service if it's clearly standalone
    if is_standalone_storage:
        req = SpecRequirement(
            category="Storage",
            raw_description=_extract_context(original_text, ["storage", "disk", "san", "nas", "s3", "ebs", "backup"]),
            quantity=1,
            unit="GB",
            value=storage_tb * 1024 if storage_tb else 0,
            source_platform=platform,
            notes=f"Type: {storage_type}, Size: {storage_tb or 'unspecified'} TB, IOPS: {iops or 'unspecified'}"
        )
        req._storage_type = storage_type
        req._storage_tb = storage_tb
        req._iops = iops
        requirements.append(req)

    # ── Database ──────────────────────────────────────────────────────────────
    db_engines = []
    for pattern in DATABASE_PATTERNS:
        matches = re.findall(pattern, text_lower)
        for m in matches:
            engine = m if isinstance(m, str) else m[0]
            engine = engine.strip().lower()
            if engine and engine not in db_engines:
                db_engines.append(engine)

    # Only add database if an engine is explicitly mentioned (not just the word "database")
    # If the spec says "Database: MongoDB" that's explicit.
    # If it just says "database" generically with no engine, check context more carefully.
    explicit_db_engines = ["postgresql", "postgres", "mysql", "mariadb", "oracle",
                           "sql server", "mssql", "mongodb", "redis", "cassandra",
                           "elasticsearch", "dynamodb"]
    
    has_explicit_db = any(eng in text_lower for eng in explicit_db_engines)
    
    if has_explicit_db:
        # Only add engines we actually found explicitly
        if not db_engines:
            # Re-scan for explicit engines
            for eng in explicit_db_engines:
                if eng in text_lower:
                    normalized = eng.replace("postgres", "postgresql") if eng == "postgres" else eng
                    if normalized not in db_engines:
                        db_engines.append(normalized)
        
        for engine in db_engines:
            req = SpecRequirement(
                category="Database",
                raw_description=_extract_context(original_text, ["database", "db", engine]),
                quantity=1,
                unit="instance",
                value=0,
                source_platform=platform,
                notes=f"Engine: {engine}"
            )
            req._db_engine = engine
            requirements.append(req)

    # ── Networking ────────────────────────────────────────────────────────────
    # ONLY create networking requirement for EXPLICIT networking services
    # (load balancer, CDN, VPN, firewall, etc.)
    # Basic connectivity (IP address, 10 Mbps bandwidth) is NOT a networking service.
    bandwidth_gbps = 0
    for pattern in NETWORK_PATTERNS:
        matches = re.findall(pattern, text_lower)
        for m in matches:
            if isinstance(m, tuple) and len(m) >= 2:
                val, unit = m[0], m[1].lower()
                try:
                    num = float(val)
                    if "gbps" in unit or "gb/s" in unit:
                        bandwidth_gbps = max(bandwidth_gbps, num)
                    elif "mbps" in unit or "mb/s" in unit:
                        bandwidth_gbps = max(bandwidth_gbps, num / 1000)
                    elif "tbps" in unit:
                        bandwidth_gbps = max(bandwidth_gbps, num * 1000)
                except (ValueError, IndexError):
                    pass

    # Only add networking if there's a specific networking SERVICE mentioned
    # (not just basic connectivity like "10 Mbps" or "1 IPv4")
    explicit_net_services = ["load balancer", "cdn", "cloudfront", "vpn", "direct connect",
                             "firewall", "waf", "transit gateway", "nat gateway"]
    has_explicit_net_service = any(kw in text_lower for kw in explicit_net_services)
    has_significant_bandwidth = bandwidth_gbps >= 1.0  # >= 1 Gbps suggests dedicated networking

    if has_explicit_net_service or has_significant_bandwidth:
        req = SpecRequirement(
            category="Networking",
            raw_description=_extract_context(original_text, ["network", "bandwidth", "load balancer", "cdn", "vpn", "firewall"]),
            quantity=1,
            unit="service",
            value=bandwidth_gbps,
            source_platform=platform,
            notes=f"Bandwidth: {bandwidth_gbps or 'unspecified'} Gbps"
        )
        req._bandwidth_gbps = bandwidth_gbps
        requirements.append(req)

    # ── GPU / AI / ML ─────────────────────────────────────────────────────────
    # ONLY add GPU if spec EXPLICITLY requires GPU instances or ML training/inference
    # Mentioning "AI" or "machine learning" in a feature description doesn't mean GPU is needed
    gpu_count = 0
    gpu_model = ""
    has_explicit_gpu_requirement = False

    for pattern in GPU_PATTERNS[:2]:  # Only the numeric GPU patterns (not keyword-only)
        matches = re.findall(pattern, text_lower)
        if matches:
            has_explicit_gpu_requirement = True
            for m in matches:
                try:
                    gpu_count = max(gpu_count, int(m))
                except (ValueError, TypeError):
                    pass

    gpu_models = ["a100", "h100", "v100", "t4", "a10", "l40", "rtx"]
    for model in gpu_models:
        if model in text_lower:
            gpu_model = model
            has_explicit_gpu_requirement = True
            break

    # Only trigger GPU category if there's an explicit GPU count, GPU model, or
    # the spec clearly describes a training/inference WORKLOAD (not just mentions AI)
    explicit_ml_workload_phrases = ["training workload", "model training", "gpu cluster",
                                    "inference endpoint", "deep learning training",
                                    "gpu instance", "gpu server"]
    has_ml_workload = any(phrase in text_lower for phrase in explicit_ml_workload_phrases)

    if has_explicit_gpu_requirement or has_ml_workload:
        req = SpecRequirement(
            category="GPU/ML",
            raw_description=_extract_context(original_text, ["gpu", "machine learning", "ai", "training", "inference"]),
            quantity=max(gpu_count, 1),
            unit="instance",
            value=gpu_count,
            source_platform=platform,
            notes=f"GPU Count: {gpu_count or 'unspecified'}, Model: {gpu_model or 'unspecified'}"
        )
        req._gpu_count = gpu_count
        req._gpu_model = gpu_model
        requirements.append(req)

    # ── Containers ────────────────────────────────────────────────────────────
    # ONLY add containers if spec explicitly requires container ORCHESTRATION
    # Mentioning "docker" alone or "container" in a description doesn't mean EKS/ECS is needed
    explicit_orchestration_keywords = ["kubernetes cluster", "k8s cluster", "eks", "ecs cluster",
                                       "container orchestration", "pod deployment", "helm chart",
                                       "openshift", "fargate task", "microservices architecture"]
    # Weak signals — only count if multiple are present
    weak_container_signals = ["docker", "container", "kubernetes", "k8s", "pod", "microservice"]
    
    strong_container = any(kw in text_lower for kw in explicit_orchestration_keywords)
    weak_count = sum(1 for kw in weak_container_signals if kw in text_lower)
    
    if strong_container or weak_count >= 3:
        req = SpecRequirement(
            category="Containers",
            raw_description=_extract_context(original_text, ["docker", "kubernetes", "container", "pod", "microservice"]),
            quantity=1,
            unit="cluster",
            source_platform=platform,
            notes="Container orchestration required"
        )
        requirements.append(req)

    # ── Serverless ────────────────────────────────────────────────────────────
    # Only if spec explicitly mentions serverless architecture or Lambda functions
    explicit_serverless = ["serverless architecture", "lambda function", "function as a service",
                           "faas", "event-driven architecture", "serverless compute"]
    # "rest api" or "api gateway" alone is NOT enough — those can run on EC2 too
    weak_serverless = ["lambda", "serverless", "api gateway"]
    
    strong_serverless = any(kw in text_lower for kw in explicit_serverless)
    weak_serverless_count = sum(1 for kw in weak_serverless if kw in text_lower)
    
    if strong_serverless or weak_serverless_count >= 2:
        req = SpecRequirement(
            category="Serverless/API",
            raw_description=_extract_context(original_text, ["lambda", "serverless", "api", "function"]),
            quantity=1,
            unit="service",
            source_platform=platform,
            notes="Serverless/API workload"
        )
        requirements.append(req)

    # ── Analytics / Data ──────────────────────────────────────────────────────
    # Only if spec explicitly describes analytics/data processing workloads
    explicit_analytics = ["data warehouse", "etl pipeline", "data lake", "big data processing",
                          "streaming pipeline", "real-time analytics", "batch processing pipeline"]
    # Weak: just mentioning "analytics" or "reporting" in a feature list isn't enough
    weak_analytics = ["redshift", "bigquery", "synapse", "spark", "hadoop", "emr", 
                      "glue", "kinesis", "data warehouse"]
    
    strong_analytics = any(kw in text_lower for kw in explicit_analytics)
    weak_analytics_count = sum(1 for kw in weak_analytics if kw in text_lower)
    
    if strong_analytics or weak_analytics_count >= 2:
        req = SpecRequirement(
            category="Analytics/Data",
            raw_description=_extract_context(original_text, ["analytics", "data", "etl", "warehouse", "streaming"]),
            quantity=1,
            unit="service",
            source_platform=platform,
            notes="Analytics/Data processing workload"
        )
        requirements.append(req)

    # ── Security / Identity ───────────────────────────────────────────────────
    # Only if spec explicitly requires security SERVICES (not just encryption or passwords)
    explicit_security_services = ["active directory", "identity provider", "sso integration",
                                  "waf deployment", "ddos protection", "siem", "security operations",
                                  "certificate management", "secrets management", "key management"]
    # "encryption" alone is a standard practice, not a separate requirement
    
    if any(kw in text_lower for kw in explicit_security_services):
        req = SpecRequirement(
            category="Security/Identity",
            raw_description=_extract_context(original_text, ["security", "identity", "encryption", "iam", "waf"]),
            quantity=1,
            unit="service",
            source_platform=platform,
            notes="Security/Identity services required"
        )
        requirements.append(req)

    # ── SaaS flag ─────────────────────────────────────────────────────────────
    if is_saas_spec and not requirements:
        req = SpecRequirement(
            category="Unknown",
            raw_description=original_text[:500],
            source_platform=platform,
            notes="This appears to be a SaaS/application requirement. Infrastructure mapping may not apply directly. Consider the application's hosting requirements instead."
        )
        requirements.append(req)

    # If nothing was detected, return a minimal "needs_info" requirement
    if not requirements:
        req = SpecRequirement(
            category="Unknown",
            raw_description=original_text[:500],
            source_platform=platform,
            notes="Could not extract specific infrastructure requirements"
        )
        requirements.append(req)

    return requirements


def _has_compute_keywords(text: str) -> bool:
    keywords = ["server", "compute", "ec2", "virtual machine", "vm ", "instance", "node", "worker",
                "web server", "app server", "application server"]
    return any(kw in text for kw in keywords)


def _has_storage_keywords(text: str) -> bool:
    keywords = ["storage", "disk", "volume", "backup", "archive", "s3", "ebs", "efs", "san", "nas"]
    return any(kw in text for kw in keywords)


def _extract_context(text: str, keywords: List[str], window: int = 300) -> str:
    """
    Find the BEST keyword occurrence and return surrounding text.
    Prefers occurrences that are near other infrastructure-related terms,
    not just the first random match in an unrelated paragraph.
    """
    text_lower = text.lower()
    
    # Infrastructure context words that indicate the surrounding text is actually about infra
    infra_context_words = ["cpu", "vcpu", "core", "ram", "memory", "gb", "tb", "server",
                           "instance", "database", "storage", "disk", "network", "bandwidth",
                           "mbps", "gbps", "vm", "virtual", "os:", "operating system",
                           "iops", "cluster", "node", "ip", "port"]
    
    best_snippet = ""
    best_score = -1
    
    for kw in keywords:
        # Find ALL occurrences of this keyword
        start_idx = 0
        while True:
            idx = text_lower.find(kw, start_idx)
            if idx < 0:
                break
            
            # Get surrounding window
            snip_start = max(0, idx - window // 2)
            snip_end = min(len(text), idx + window // 2)
            snippet = text[snip_start:snip_end].strip()
            snippet_lower = snippet.lower()
            
            # Score this snippet by how many infrastructure context words it contains
            score = sum(1 for cw in infra_context_words if cw in snippet_lower)
            
            if score > best_score:
                best_score = score
                best_snippet = snippet
            
            start_idx = idx + len(kw)
    
    # If no good context found (score 0 = keyword appeared in unrelated text), 
    # return empty rather than misleading text
    if best_score < 2:
        # Try to find any line with actual numbers + units (likely a spec table row)
        for line in text.split("\n"):
            line_lower = line.lower().strip()
            if any(cw in line_lower for cw in infra_context_words) and re.search(r'\d+', line_lower):
                return line.strip()[:400]
        return ""
    
    return best_snippet if best_snippet else ""


def _map_requirement(req: SpecRequirement, region: str = "us-east-1") -> AWSServiceMapping:
    """Map a single SpecRequirement to an AWS service recommendation."""
    cat = req.category
    if cat == "Compute":        return _map_compute(req, region)
    elif cat == "Storage":      return _map_storage(req, region)
    elif cat == "Database":     return _map_database(req, region)
    elif cat == "Networking":   return _map_networking(req, region)
    elif cat == "GPU/ML":       return _map_gpu_ml(req, region)
    elif cat == "Containers":   return _map_containers(req, region)
    elif cat == "Serverless/API": return _map_serverless(req, region)
    elif cat == "Analytics/Data": return _map_analytics(req, region)
    elif cat == "Security/Identity": return _map_security(req, region)
    else:                       return _map_unknown(req)


def _map_compute(req: SpecRequirement, region: str = "us-east-1") -> AWSServiceMapping:
    vcpu = getattr(req, "_vcpu", 0)
    ram_gb = getattr(req, "_ram_gb", 0)
    missing = []

    if vcpu == 0:
        missing.append("Number of vCPUs per instance")
    if ram_gb == 0:
        missing.append("RAM per instance (GB)")

    x86_type = "m6i.large"
    graviton_type = "m7g.large"

    for min_vcpu, min_ram, x86, grav, _ in EC2_SIZE_MAP:
        if vcpu >= min_vcpu or ram_gb >= min_ram:
            x86_type = x86
            graviton_type = grav

    base_monthly = EC2_MONTHLY_PRICES.get(x86_type, 70.08) * req.quantity
    
    # Include EBS gp3 storage cost if disk space was mentioned in the spec
    # (since we no longer create a separate Storage category for local disk)
    ebs_cost = 0.0
    disk_note = ""
    raw_text = (req.raw_description or "").lower()
    # Try to extract disk size from the raw spec text
    disk_match = re.search(r'(\d+)\s*(gb|tb)\s*(?:disk|storage|ssd|hdd|nvme|space)', raw_text)
    if not disk_match:
        disk_match = re.search(r'(?:disk|storage|space)[:\s]+(\d+)\s*(gb|tb)', raw_text)
    if disk_match:
        disk_val = float(disk_match.group(1))
        disk_unit = disk_match.group(2).lower()
        disk_gb = disk_val if disk_unit == "gb" else disk_val * 1024
        ebs_cost = disk_gb * EC2_MONTHLY_PRICES["ebs_gp3_per_gb"]
        disk_note = f", EBS: {int(disk_gb)} GB gp3 included"

    total_base = base_monthly + ebs_cost
    monthly = apply_region(total_base, region)
    
    description = f"EC2 instance ({x86_type}) — {req.notes}{disk_note}"
    if ebs_cost > 0:
        description += f" | Includes EC2 + EBS storage"

    # Build reasoning/justification
    reasoning = f"Detected: {vcpu} vCPU, {ram_gb} GB RAM from spec."
    if ebs_cost > 0:
        reasoning += f" Includes {int(disk_gb)} GB EBS gp3 storage."
    reasoning += f" Selected {x86_type} as the smallest instance meeting these requirements."
    if req.quantity > 1:
        reasoning += f" Quantity: {req.quantity} instances as specified."
    else:
        reasoning += " Single instance — no multi-instance or HA requirement detected."

    return AWSServiceMapping(
        requirement=req,
        service_name="Amazon EC2",
        service_code="AmazonEC2",
        recommended_type=x86_type,
        description=description,
        quantity=req.quantity,
        unit="instance",
        confidence="high" if vcpu > 0 and ram_gb > 0 else ("medium" if vcpu > 0 or ram_gb > 0 else "needs_info"),
        missing_info=missing,
        alternatives=[
            {"label": "Graviton3 (ARM, ~20% cheaper)", "type": graviton_type,
             "monthly_usd": apply_region(round((EC2_MONTHLY_PRICES.get(graviton_type, 60.0) * req.quantity + ebs_cost), 2), region),
             "base_monthly_usd": round(EC2_MONTHLY_PRICES.get(graviton_type, 60.0) * req.quantity + ebs_cost, 2)},
            {"label": "Spot Instances (~70% cheaper, interruptible)", "type": f"{x86_type} Spot",
             "monthly_usd": round(apply_region(base_monthly * 0.3 + ebs_cost, region), 2),
             "base_monthly_usd": round(base_monthly * 0.3 + ebs_cost, 2)},
            {"label": "1-Year Reserved (~30% savings on compute)", "type": f"{x86_type} Reserved 1yr",
             "monthly_usd": round(apply_region(base_monthly * 0.70 + ebs_cost, region), 2),
             "base_monthly_usd": round(base_monthly * 0.70 + ebs_cost, 2)},
            {"label": "3-Year Reserved (~45% savings on compute)", "type": f"{x86_type} Reserved 3yr",
             "monthly_usd": round(apply_region(base_monthly * 0.55 + ebs_cost, region), 2),
             "base_monthly_usd": round(base_monthly * 0.55 + ebs_cost, 2)},
        ],
        pricing_options=get_pricing_models("AmazonEC2"),
        monthly_estimate_usd=round(monthly, 2),
        base_monthly_usd=round(total_base, 2),
        aws_calculator_url=get_calculator_url("AmazonEC2"),
        region=region,
        reasoning=reasoning,
    )


def _map_storage(req: SpecRequirement, region: str = "us-east-1") -> AWSServiceMapping:
    storage_type = getattr(req, "_storage_type", "general")
    storage_tb = getattr(req, "_storage_tb", 0)
    iops = getattr(req, "_iops", 0)
    storage_gb = storage_tb * 1024 if storage_tb else req.value

    missing = []
    if storage_gb == 0:
        missing.append("Total storage capacity (GB/TB)")

    if storage_type == "object":
        service_name = "Amazon S3"
        service_code = "AmazonS3"
        rec_type = "S3 Standard"
        price = EC2_MONTHLY_PRICES["s3_standard_per_gb"] * max(storage_gb, 100)
        alts = [
            {"label": "S3 Standard-IA (infrequent access, ~46% cheaper)", "type": "S3 Standard-IA",
             "monthly_usd": round(0.0125 * max(storage_gb, 100), 2)},
            {"label": "S3 Glacier Instant Retrieval (archive)", "type": "S3 Glacier Instant",
             "monthly_usd": round(0.004 * max(storage_gb, 100), 2)},
            {"label": "S3 Intelligent-Tiering (auto-optimize)", "type": "S3 Intelligent-Tiering",
             "monthly_usd": round(0.023 * max(storage_gb, 100), 2)},
        ]
    elif storage_type == "block":
        service_name = "Amazon EBS"
        service_code = "AmazonEC2"
        rec_type = "gp3"
        price = EC2_MONTHLY_PRICES["ebs_gp3_per_gb"] * max(storage_gb, 100)
        alts = [
            {"label": "io2 Block Express (high IOPS, mission-critical)", "type": "io2 Block Express",
             "monthly_usd": round(0.125 * max(storage_gb, 100), 2)},
            {"label": "gp2 (previous gen)", "type": "gp2",
             "monthly_usd": round(0.10 * max(storage_gb, 100), 2)},
            {"label": "st1 (throughput optimized HDD, big data)", "type": "st1",
             "monthly_usd": round(0.045 * max(storage_gb, 100), 2)},
        ]
    elif storage_type == "file":
        service_name = "Amazon EFS"
        service_code = "AmazonEFS"
        rec_type = "EFS Standard"
        price = EC2_MONTHLY_PRICES["efs_per_gb"] * max(storage_gb, 100)
        alts = [
            {"label": "Amazon FSx for Windows (SMB/CIFS)", "type": "FSx for Windows",
             "monthly_usd": round(0.13 * max(storage_gb, 100), 2)},
            {"label": "Amazon FSx for NetApp ONTAP", "type": "FSx for ONTAP",
             "monthly_usd": round(0.13 * max(storage_gb, 100), 2)},
            {"label": "Amazon FSx for Lustre (HPC)", "type": "FSx for Lustre",
             "monthly_usd": round(0.14 * max(storage_gb, 100), 2)},
        ]
    elif storage_type == "archive":
        service_name = "Amazon S3 Glacier"
        service_code = "AmazonGlacier"
        rec_type = "Glacier Deep Archive"
        price = EC2_MONTHLY_PRICES["glacier_per_gb"] * max(storage_gb, 100)
        alts = [
            {"label": "S3 Glacier Instant Retrieval (faster restore)", "type": "S3 Glacier Instant",
             "monthly_usd": round(0.004 * max(storage_gb, 100), 2)},
        ]
    else:
        service_name = "Amazon S3"
        service_code = "AmazonS3"
        rec_type = "S3 Standard"
        price = EC2_MONTHLY_PRICES["s3_standard_per_gb"] * max(storage_gb, 100)
        alts = [
            {"label": "Amazon EBS gp3 (block storage)", "type": "EBS gp3",
             "monthly_usd": round(0.08 * max(storage_gb, 100), 2)},
            {"label": "Amazon EFS (shared file system)", "type": "EFS Standard",
             "monthly_usd": round(0.30 * max(storage_gb, 100), 2)},
        ]
        missing.append("Preferred storage type (object / block / file / archive)")

    return AWSServiceMapping(
        requirement=req,
        service_name=service_name,
        service_code=service_code,
        recommended_type=rec_type,
        description=f"Storage service — {req.notes}",
        quantity=1,
        unit="GB",
        confidence="high" if storage_gb > 0 and storage_type != "general" else "medium",
        missing_info=missing,
        alternatives=[{"label": a["label"], "type": a["type"],
                       "monthly_usd": apply_region(a["monthly_usd"], region),
                       "base_monthly_usd": round(a["monthly_usd"], 2)} for a in alts],
        pricing_options=get_pricing_models(service_code),
        monthly_estimate_usd=apply_region(round(price, 2), region),
        base_monthly_usd=round(price, 2),
        aws_calculator_url=get_calculator_url(service_code),
        region=region,
    )


def _map_database(req: SpecRequirement, region: str = "us-east-1") -> AWSServiceMapping:
    engine = getattr(req, "_db_engine", "unspecified").lower()
    missing = []

    # ── Determine if this is a simple single-instance DB or a managed service need ──
    # For a single server with a DB (like "Database: MongoDB" on one machine),
    # the best AWS solution is often EC2 self-managed, NOT a managed service.
    # Managed services (RDS, DocumentDB) are best when:
    # - HA/Multi-AZ is needed
    # - Multiple replicas are specified
    # - "managed" or "serverless" is mentioned
    # - No specific OS requirement (managed services abstract the OS)
    
    text_lower = req.raw_description.lower() if req.raw_description else ""
    notes_lower = req.notes.lower() if req.notes else ""
    
    needs_managed = any(kw in text_lower or kw in notes_lower for kw in [
        "high availability", "multi-az", "replica", "cluster", "managed",
        "serverless", "automated backup", "auto-scaling", "read replica"
    ])
    
    # If it's a simple single-instance DB on a server, recommend EC2 self-managed
    is_simple_single_instance = not needs_managed

    # ── Engine-specific mapping ───────────────────────────────────────────────
    # Managed service options (for when HA/managed is needed)
    managed_engine_map = {
        "postgresql": ("Amazon RDS for PostgreSQL", "AmazonRDS", "db.m6i.large", EC2_MONTHLY_PRICES["rds_postgres_per_hour"] * 730),
        "postgres": ("Amazon RDS for PostgreSQL", "AmazonRDS", "db.m6i.large", EC2_MONTHLY_PRICES["rds_postgres_per_hour"] * 730),
        "mysql": ("Amazon RDS for MySQL", "AmazonRDS", "db.m6i.large", EC2_MONTHLY_PRICES["rds_mysql_per_hour"] * 730),
        "mariadb": ("Amazon RDS for MariaDB", "AmazonRDS", "db.m6i.large", EC2_MONTHLY_PRICES["rds_mysql_per_hour"] * 730),
        "oracle": ("Amazon RDS for Oracle", "AmazonRDS", "db.m6i.large", EC2_MONTHLY_PRICES["rds_oracle_per_hour"] * 730),
        "sql server": ("Amazon RDS for SQL Server", "AmazonRDS", "db.m5.large", EC2_MONTHLY_PRICES["rds_sqlserver_per_hour"] * 730),
        "mssql": ("Amazon RDS for SQL Server", "AmazonRDS", "db.m5.large", EC2_MONTHLY_PRICES["rds_sqlserver_per_hour"] * 730),
        "mongodb": ("Amazon DocumentDB", "AmazonDocDB", "db.r6g.large", 185.0),
        "redis": ("Amazon ElastiCache for Redis", "AmazonElastiCache", "cache.r7g.large", EC2_MONTHLY_PRICES["elasticache_redis_per_hour"] * 730),
        "cassandra": ("Amazon Keyspaces (Apache Cassandra)", "AmazonKeyspaces", "Serverless", 25.0),
        "elasticsearch": ("Amazon OpenSearch Service", "AmazonOpenSearch", "r6g.large.search", 120.0),
        "dynamodb": ("Amazon DynamoDB", "AmazonDynamoDB", "Provisioned / On-Demand", 25.0),
    }

    # Self-managed on EC2 options (simpler, cheaper for single instances)
    selfmanaged_engine_map = {
        "postgresql": ("Amazon EC2 (self-managed PostgreSQL)", "AmazonEC2", "m6i.large", 70.08),
        "postgres": ("Amazon EC2 (self-managed PostgreSQL)", "AmazonEC2", "m6i.large", 70.08),
        "mysql": ("Amazon EC2 (self-managed MySQL)", "AmazonEC2", "m6i.large", 70.08),
        "mariadb": ("Amazon EC2 (self-managed MariaDB)", "AmazonEC2", "m6i.large", 70.08),
        "mongodb": ("Amazon EC2 (self-managed MongoDB)", "AmazonEC2", "m6i.xlarge", 140.16),
        "redis": ("Amazon EC2 (self-managed Redis)", "AmazonEC2", "r6i.large", 100.0),
        "cassandra": ("Amazon EC2 (self-managed Cassandra)", "AmazonEC2", "m6i.xlarge", 140.16),
        "elasticsearch": ("Amazon EC2 (self-managed Elasticsearch)", "AmazonEC2", "r6i.large", 100.0),
    }

    if is_simple_single_instance and engine in selfmanaged_engine_map:
        # Recommend self-managed (cheaper, simpler for single-instance)
        svc_name, svc_code, rec_type, monthly = selfmanaged_engine_map[engine]
        confidence = "high"
        description = f"Self-managed {engine} on EC2 — best for single-instance, cost-optimized deployments"
        
        # Offer managed service as an alternative
        if engine in managed_engine_map:
            managed = managed_engine_map[engine]
            alts = [
                {"label": f"{managed[0]} (managed, HA-ready)", "type": managed[2],
                 "monthly_usd": apply_region(round(managed[3], 2), region),
                 "base_monthly_usd": round(managed[3], 2)},
                {"label": "Graviton EC2 (~20% cheaper)", "type": rec_type.replace("m6i", "m7g").replace("r6i", "r7g"),
                 "monthly_usd": apply_region(round(monthly * 0.80, 2), region),
                 "base_monthly_usd": round(monthly * 0.80, 2)},
                {"label": "Reserved 1yr (~30% savings)", "type": f"{rec_type} Reserved 1yr",
                 "monthly_usd": apply_region(round(monthly * 0.70, 2), region),
                 "base_monthly_usd": round(monthly * 0.70, 2)},
            ]
        else:
            alts = []
    elif engine in managed_engine_map:
        svc_name, svc_code, rec_type, monthly = managed_engine_map[engine]
        confidence = "high"
        description = f"Managed database service — Engine: {engine}"
        alts = [
            {"label": "Multi-AZ (high availability, ~2x cost)", "type": f"{rec_type} Multi-AZ",
             "monthly_usd": apply_region(round(monthly * 2, 2), region),
             "base_monthly_usd": round(monthly * 2, 2)},
            {"label": "Reserved Instance 1yr (~30% savings)", "type": f"{rec_type} Reserved 1yr",
             "monthly_usd": apply_region(round(monthly * 0.70, 2), region),
             "base_monthly_usd": round(monthly * 0.70, 2)},
            {"label": "Graviton-based (~20% cheaper)", "type": "db.m7g.large",
             "monthly_usd": apply_region(round(monthly * 0.80, 2), region),
             "base_monthly_usd": round(monthly * 0.80, 2)},
        ]
        # For engines that can also be self-managed, add that as a cheaper alt
        if engine in selfmanaged_engine_map:
            sm = selfmanaged_engine_map[engine]
            alts.insert(0, {"label": f"EC2 self-managed (cheaper, no managed overhead)", "type": sm[2],
                            "monthly_usd": apply_region(round(sm[3], 2), region),
                            "base_monthly_usd": round(sm[3], 2)})
    elif engine == "unspecified":
        svc_name = "Amazon RDS"
        svc_code = "AmazonRDS"
        rec_type = "db.m6i.large"
        monthly = EC2_MONTHLY_PRICES["rds_mysql_per_hour"] * 730
        confidence = "needs_info"
        description = "Database service — engine unspecified"
        missing = ["Database engine type (MySQL, PostgreSQL, SQL Server, Oracle, MongoDB, etc.)",
                   "Database size and instance sizing requirements"]
        alts = []
    else:
        svc_name = "Amazon RDS"
        svc_code = "AmazonRDS"
        rec_type = "db.m6i.large"
        monthly = EC2_MONTHLY_PRICES["rds_mysql_per_hour"] * 730
        confidence = "medium"
        description = f"Database service — Engine: {engine}"
        missing.append("Confirm engine compatibility with Amazon RDS")
        alts = []

    # Build reasoning/justification
    if is_simple_single_instance and engine in selfmanaged_engine_map:
        reasoning = f"Detected: {engine} database. Single-instance deployment (no HA/cluster/managed keywords found). Recommended self-managed on EC2 for cost efficiency. Managed service ({managed_engine_map.get(engine, ('',))[0]}) available as alternative if HA is needed later."
    elif engine in managed_engine_map and not is_simple_single_instance:
        reasoning = f"Detected: {engine} database with managed/HA requirements. Recommended {svc_name} for automated backups, patching, and high availability."
    elif engine == "unspecified":
        reasoning = "Database engine not specified in the spec. Please provide the engine type for a more accurate recommendation."
    else:
        reasoning = f"Detected: {engine} database. Mapped to {svc_name} as the closest AWS equivalent."

    return AWSServiceMapping(
        requirement=req,
        service_name=svc_name,
        service_code=svc_code,
        recommended_type=rec_type,
        description=description,
        quantity=req.quantity,
        unit="instance",
        confidence=confidence,
        missing_info=missing,
        alternatives=alts,
        pricing_options=get_pricing_models(svc_code),
        monthly_estimate_usd=apply_region(round(monthly, 2), region),
        base_monthly_usd=round(monthly, 2),
        aws_calculator_url=get_calculator_url(svc_code),
        region=region,
        reasoning=reasoning,
    )


def _map_networking(req: SpecRequirement, region: str = "us-east-1") -> AWSServiceMapping:
    bandwidth_gbps = getattr(req, "_bandwidth_gbps", 0)
    text = req.raw_description.lower()

    services = []
    base_monthly = 0.0

    if any(kw in text for kw in ["load balancer", "alb", "nlb", "elb"]):
        services.append("Elastic Load Balancing (ALB)")
        base_monthly += 22.0
    if any(kw in text for kw in ["cdn", "cloudfront", "content delivery"]):
        services.append("Amazon CloudFront")
        base_monthly += 85.0
    if any(kw in text for kw in ["vpn", "site-to-site vpn"]):
        services.append("AWS Site-to-Site VPN")
        base_monthly += 36.0
    if any(kw in text for kw in ["direct connect", "mpls", "expressroute", "interconnect"]):
        services.append("AWS Direct Connect")
        base_monthly += 220.0
    if any(kw in text for kw in ["firewall", "network firewall"]):
        services.append("AWS Network Firewall")
        base_monthly += 65.0
    if any(kw in text for kw in ["waf", "web application firewall"]):
        services.append("AWS WAF")
        base_monthly += 30.0
    if any(kw in text for kw in ["dns", "route 53"]):
        services.append("Amazon Route 53")
        base_monthly += 1.0
    if any(kw in text for kw in ["nat gateway", "nat"]):
        services.append("NAT Gateway")
        base_monthly += 45.0

    if not services:
        services = ["Amazon VPC (default)"]
        base_monthly = 0.0

    missing = []
    if bandwidth_gbps == 0:
        missing.append("Expected network bandwidth requirements (Gbps/Mbps)")

    monthly = apply_region(base_monthly, region)

    # Build reasoning/justification
    reasoning = f"Detected explicit networking services: {', '.join(services)}."
    if bandwidth_gbps > 0:
        reasoning += f" Bandwidth requirement: {bandwidth_gbps} Gbps."

    return AWSServiceMapping(
        requirement=req,
        service_name=", ".join(services[:2]) if services else "Amazon VPC",
        service_code="AmazonVPC",
        recommended_type=", ".join(services),
        description=f"Networking services — {req.notes}",
        quantity=1,
        unit="service bundle",
        confidence="medium" if missing else "high",
        missing_info=missing,
        alternatives=[
            {"label": "AWS Transit Gateway (multi-VPC connectivity)", "type": "Transit Gateway",
             "monthly_usd": apply_region(36.0, region),
             "base_monthly_usd": 36.0},
            {"label": "AWS PrivateLink (private endpoint)", "type": "PrivateLink",
             "monthly_usd": apply_region(8.0, region),
             "base_monthly_usd": 8.0},
            {"label": "AWS Global Accelerator (performance)", "type": "Global Accelerator",
             "monthly_usd": apply_region(18.0, region),
             "base_monthly_usd": 18.0},
        ],
        pricing_options=get_pricing_models("ElasticLoadBalancing"),
        monthly_estimate_usd=round(monthly, 2),
        base_monthly_usd=round(base_monthly, 2),
        aws_calculator_url=get_calculator_url("ElasticLoadBalancing"),
        region=region,
        reasoning=reasoning,
    )


def _map_gpu_ml(req: SpecRequirement, region: str = "us-east-1") -> AWSServiceMapping:
    gpu_count = getattr(req, "_gpu_count", 1)
    gpu_model = getattr(req, "_gpu_model", "")
    text = req.raw_description.lower()

    # Map GPU model to EC2 instance
    gpu_instance_map = {
        "a100": ("p4d.24xlarge", 9754.56),
        "h100": ("p5.48xlarge", 98000.0),
        "v100": ("p3.2xlarge", 2203.20),
        "t4": ("g4dn.xlarge", 378.43),
        "a10": ("g5.xlarge", 604.80),
        "l40": ("g6.xlarge", 700.0),
    }

    if gpu_model in gpu_instance_map:
        rec_type, base_monthly = gpu_instance_map[gpu_model]
        base_monthly *= max(gpu_count, 1)
    elif "inference" in text:
        rec_type = "inf2.xlarge"
        base_monthly = 324.0 * max(gpu_count, 1)
    elif "training" in text:
        rec_type = "p4d.24xlarge"
        base_monthly = 9754.56 * max(gpu_count, 1)
    else:
        rec_type = "g4dn.xlarge"
        base_monthly = 378.43 * max(gpu_count, 1)

    monthly = apply_region(base_monthly, region)

    missing = []
    if not gpu_model:
        missing.append("GPU model/type (A100, H100, V100, T4, etc.)")
    if gpu_count == 0:
        missing.append("Number of GPUs required")
    if not any(kw in text for kw in ["training", "inference", "fine-tuning"]):
        missing.append("Workload type (training, inference, fine-tuning)")

    return AWSServiceMapping(
        requirement=req,
        service_name="Amazon EC2 (GPU) / Amazon SageMaker",
        service_code="AmazonEC2",
        recommended_type=rec_type,
        description=f"GPU/ML compute — {req.notes}",
        quantity=req.quantity,
        unit="instance",
        confidence="medium" if missing else "high",
        missing_info=missing,
        alternatives=[
            {"label": "Amazon SageMaker (managed ML platform)", "type": "SageMaker Training Jobs",
             "monthly_usd": apply_region(round(base_monthly * 1.2, 2), region)},
            {"label": "AWS Inferentia (inference, cost-optimized)", "type": "inf2.xlarge",
             "monthly_usd": apply_region(324.0, region)},
            {"label": "AWS Trainium (training, cost-optimized)", "type": "trn1.2xlarge",
             "monthly_usd": apply_region(1000.0, region)},
            {"label": "Amazon Bedrock (serverless LLM API)", "type": "Bedrock (pay-per-token)",
             "monthly_usd": apply_region(50.0, region)},
        ],
        pricing_options=["On-Demand", "Spot (up to 90% cheaper for training)", "Reserved 1yr", "Savings Plans"],
        monthly_estimate_usd=round(monthly, 2),
        base_monthly_usd=round(base_monthly, 2),
        aws_calculator_url=get_calculator_url("AmazonEC2"),
        region=region,
    )


def _map_containers(req: SpecRequirement, region: str = "us-east-1") -> AWSServiceMapping:
    text = req.raw_description.lower()
    missing = []

    if "kubernetes" in text or "k8s" in text or "eks" in text or "openshift" in text:
        svc = "Amazon EKS"
        rec_type = "Managed node group (m7g.large)"
        base_monthly = EC2_MONTHLY_PRICES["eks_cluster_per_hour"] * 730 + EC2_MONTHLY_PRICES["m7g.large"] * 2
    elif "fargate" in text or "serverless container" in text:
        svc = "AWS Fargate"
        rec_type = "Fargate (0.25 vCPU, 0.5 GB)"
        base_monthly = 15.0
    else:
        svc = "Amazon ECS / Amazon EKS"
        rec_type = "ECS with Fargate"
        base_monthly = 73.0
        missing.append("Container orchestrator preference (ECS/EKS/Fargate)")

    if not any(kw in text for kw in ["pod", "task", "service", "deployment"]):
        missing.append("Number of containers/pods and resource requirements per container")

    monthly = apply_region(base_monthly, region)

    return AWSServiceMapping(
        requirement=req,
        service_name=svc,
        service_code="AmazonEKS" if "EKS" in svc else "AmazonECS",
        recommended_type=rec_type,
        description="Container orchestration service",
        quantity=1,
        unit="cluster",
        confidence="medium" if missing else "high",
        missing_info=missing,
        alternatives=[
            {"label": "AWS Fargate (serverless containers, no node management)", "type": "Fargate",
             "monthly_usd": apply_region(30.0, region),
             "base_monthly_usd": 30.0},
            {"label": "Amazon ECS (simpler than EKS)", "type": "ECS",
             "monthly_usd": apply_region(60.0, region),
             "base_monthly_usd": 60.0},
            {"label": "AWS App Runner (fully managed containers)", "type": "App Runner",
             "monthly_usd": apply_region(40.0, region),
             "base_monthly_usd": 40.0},
        ],
        pricing_options=get_pricing_models("AmazonEKS" if "EKS" in svc else "AmazonECS"),
        monthly_estimate_usd=round(monthly, 2),
        base_monthly_usd=round(base_monthly, 2),
        aws_calculator_url=get_calculator_url("AmazonEKS" if "EKS" in svc else "AmazonECS"),
        region=region,
    )


def _map_serverless(req: SpecRequirement, region: str = "us-east-1") -> AWSServiceMapping:
    text = req.raw_description.lower()
    base_monthly = 5.0  # baseline

    if "api gateway" in text or "rest api" in text or "graphql" in text:
        base_monthly += 10.0

    monthly = apply_region(base_monthly, region)

    return AWSServiceMapping(
        requirement=req,
        service_name="AWS Lambda + Amazon API Gateway",
        service_code="AWSLambda",
        recommended_type="Lambda (128MB–10GB RAM)",
        description="Serverless compute and API management",
        quantity=1,
        unit="service",
        confidence="medium",
        missing_info=["Expected invocations per month", "Function memory and timeout requirements"],
        alternatives=[
            {"label": "AWS App Runner (container-based serverless)", "type": "App Runner",
             "monthly_usd": apply_region(25.0, region),
             "base_monthly_usd": 25.0},
            {"label": "AWS Step Functions (workflow orchestration)", "type": "Step Functions",
             "monthly_usd": apply_region(10.0, region),
             "base_monthly_usd": 10.0},
        ],
        pricing_options=get_pricing_models("AWSLambda"),
        monthly_estimate_usd=round(monthly, 2),
        base_monthly_usd=round(base_monthly, 2),
        aws_calculator_url=get_calculator_url("AWSLambda"),
        region=region,
    )


def _map_analytics(req: SpecRequirement, region: str = "us-east-1") -> AWSServiceMapping:
    text = req.raw_description.lower()
    base_monthly = 50.0

    if "data warehouse" in text or "redshift" in text or "synapse" in text or "bigquery" in text:
        svc = "Amazon Redshift"
        base_monthly = 300.0
    elif "streaming" in text or "kinesis" in text or "kafka" in text or "event hub" in text:
        svc = "Amazon Kinesis / Amazon MSK"
        base_monthly = 120.0
    elif "etl" in text or "glue" in text or "data factory" in text:
        svc = "AWS Glue"
        base_monthly = 45.0
    elif "big data" in text or "hadoop" in text or "spark" in text or "emr" in text:
        svc = "Amazon EMR"
        base_monthly = 200.0
    elif "data lake" in text:
        svc = "Amazon S3 + AWS Lake Formation"
        base_monthly = 100.0
    else:
        svc = "Amazon Redshift / AWS Glue"
        base_monthly = 200.0

    monthly = apply_region(base_monthly, region)

    return AWSServiceMapping(
        requirement=req,
        service_name=svc,
        service_code="AmazonRedshift",
        recommended_type="RA3.xlplus (Redshift) / Standard (Glue)",
        description="Analytics and data processing services",
        quantity=1,
        unit="service",
        confidence="medium",
        missing_info=["Data volume (GB/TB per day)", "Query concurrency requirements"],
        alternatives=[
            {"label": "Amazon Athena (serverless SQL, pay-per-query)", "type": "Athena",
             "monthly_usd": apply_region(25.0, region),
             "base_monthly_usd": 25.0},
            {"label": "Amazon OpenSearch Service (search + analytics)", "type": "OpenSearch",
             "monthly_usd": apply_region(120.0, region),
             "base_monthly_usd": 120.0},
            {"label": "Amazon QuickSight (BI and dashboards)", "type": "QuickSight",
             "monthly_usd": apply_region(18.0, region),
             "base_monthly_usd": 18.0},
        ],
        pricing_options=get_pricing_models("AmazonRedshift"),
        monthly_estimate_usd=round(monthly, 2),
        base_monthly_usd=round(base_monthly, 2),
        aws_calculator_url=get_calculator_url("AmazonRedshift"),
        region=region,
    )


def _map_security(req: SpecRequirement, region: str = "us-east-1") -> AWSServiceMapping:
    base_monthly = 25.0
    monthly = apply_region(base_monthly, region)

    return AWSServiceMapping(
        requirement=req,
        service_name="AWS IAM / AWS Secrets Manager / AWS WAF",
        service_code="AWSSecurityHub",
        recommended_type="Standard tier",
        description="Security, identity, and compliance services",
        quantity=1,
        unit="service bundle",
        confidence="medium",
        missing_info=["Compliance framework (PCI DSS, HIPAA, SOC2, etc.)", "Identity provider integration requirements"],
        alternatives=[
            {"label": "AWS IAM Identity Center (SSO)", "type": "IAM Identity Center",
             "monthly_usd": 0.0,
             "base_monthly_usd": 0.0},
            {"label": "AWS Shield Advanced (DDoS protection)", "type": "Shield Advanced",
             "monthly_usd": apply_region(3000.0, region),
             "base_monthly_usd": 3000.0},
            {"label": "Amazon GuardDuty (threat detection)", "type": "GuardDuty",
             "monthly_usd": apply_region(30.0, region),
             "base_monthly_usd": 30.0},
            {"label": "AWS Security Hub (central security view)", "type": "Security Hub",
             "monthly_usd": apply_region(15.0, region),
             "base_monthly_usd": 15.0},
        ],
        pricing_options=get_pricing_models("AWSSecurityHub"),
        monthly_estimate_usd=round(monthly, 2),
        base_monthly_usd=round(base_monthly, 2),
        aws_calculator_url=get_calculator_url("AWSSecurityHub"),
        region=region,
    )


def _map_unknown(req: SpecRequirement) -> AWSServiceMapping:
    reasoning = "No specific infrastructure requirements could be extracted from the text. Please provide more details about compute, storage, database, or networking needs."
    return AWSServiceMapping(
        requirement=req,
        service_name="AWS (service undetermined)",
        service_code="Unknown",
        recommended_type="TBD",
        description="Could not determine specific AWS service from specification",
        quantity=1,
        unit="service",
        confidence="needs_info",
        missing_info=[
            "Describe the workload type (web app, database, batch processing, etc.)",
            "Specify compute requirements (CPU, memory, instances)",
            "Specify storage requirements (size, type, IOPS)",
            "Specify expected throughput and concurrency",
        ],
        alternatives=[],
        pricing_options=[],
        monthly_estimate_usd=0.0,
        base_monthly_usd=0.0,
        aws_calculator_url="https://calculator.aws/#/createCalculator",
        reasoning=reasoning,
    )


def _mapping_to_dict(m: AWSServiceMapping) -> dict:
    sku_specs = get_sku_specs(m.recommended_type)
    return {
        "category": m.requirement.category,
        "service_name": m.service_name,
        "service_code": m.service_code,
        "recommended_type": m.recommended_type,
        "recommended_type_specs": sku_specs,
        "description": m.description,
        "quantity": m.quantity,
        "unit": m.unit,
        "confidence": m.confidence,
        "missing_info": m.missing_info,
        "alternatives": m.alternatives,
        "pricing_options": m.pricing_options,
        "service_types": get_service_types(m.service_code),
        "monthly_estimate_usd": m.monthly_estimate_usd,
        "base_monthly_usd": m.base_monthly_usd,
        "aws_calculator_url": m.aws_calculator_url,
        "region": m.region,
        "region_available": is_service_available(m.service_code, m.region),
        "raw_description": m.requirement.raw_description[:300],
        "notes": m.requirement.notes,
        "source_platform": m.requirement.source_platform,
        "reasoning": m.reasoning,
        "extracted_requirement": m.requirement.raw_description[:500] if m.requirement.raw_description.strip() else "",
        # User-selectable fields (defaults)
        "selected_type": m.recommended_type,
        "selected_pricing": m.pricing_options[0] if m.pricing_options else "On-Demand",
        "selected_quantity": m.quantity,
        "selected_monthly_usd": m.monthly_estimate_usd,
    }


def _build_summary(platform: str, mappings: List[AWSServiceMapping], confidence: str) -> str:
    platform_labels = {
        "azure": "Microsoft Azure",
        "gcp": "Google Cloud Platform",
        "onprem": "On-Premises infrastructure",
        "generic": "generic infrastructure",
    }
    source = platform_labels.get(platform, "generic infrastructure")
    count = len(mappings)
    verdict = {
        "high": "✅ AWS can fully support these requirements.",
        "medium": "⚠️ AWS can likely support these requirements — some details need confirmation.",
        "needs_info": "❓ More information needed to make accurate AWS service recommendations.",
    }.get(confidence, "")

    return f"Analyzed {source} specification. Found {count} service area(s). {verdict}"
