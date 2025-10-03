#!/usr/bin/env python3
"""
AWS CDK App for OpenSearch Trending Queries Architecture
"""
import os
import aws_cdk as cdk
from opensearch_trending_queries.opensearch_trending_queries_stack import OpenSearchTrendingQueriesStack

app = cdk.App()

# Get environment configuration
env_name = app.node.try_get_context("env") or "dev"
account = os.environ.get("CDK_DEFAULT_ACCOUNT")
region = os.environ.get("CDK_DEFAULT_REGION", "us-east-1")

# Environment configuration
env = cdk.Environment(account=account, region=region)

# Create the main stack
OpenSearchTrendingQueriesStack(
    app, 
    f"OpenSearchTrendingQueries-{env_name}",
    env=env,
    env_name=env_name,
    description="AWS infrastructure for OpenSearch trending queries analysis"
)

app.synth()