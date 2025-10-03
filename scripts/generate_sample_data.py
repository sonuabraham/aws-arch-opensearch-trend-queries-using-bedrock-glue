#!/usr/bin/env python3
"""
Sample Data Generator for OpenSearch Trending Queries System

This script generates realistic search query logs and ingests them into the system
for testing purposes. It supports various data generation patterns and volumes.
"""

import argparse
import boto3
import json
import random
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any
import sys

# Sample search queries with realistic distribution
SEARCH_QUERIES = {
    "technology": [
        "machine learning tutorial",
        "python programming",
        "aws cloud services",
        "docker containers",
        "kubernetes deployment",
        "react javascript framework",
        "typescript best practices",
        "microservices architecture",
        "api design patterns",
        "database optimization"
    ],
    "education": [
        "online courses",
        "data science certification",
        "web development bootcamp",
        "computer science degree",
        "coding tutorials",
        "learn programming",
        "software engineering career",
        "tech interview preparation",
        "algorithm practice",
        "system design interview"
    ],
    "business": [
        "cloud cost optimization",
        "devops best practices",
        "agile methodology",
        "project management tools",
        "team collaboration software",
        "business intelligence",
        "data analytics platform",
        "enterprise architecture",
        "digital transformation",
        "it infrastructure"
    ],
    "tools": [
        "git version control",
        "jenkins ci cd",
        "terraform infrastructure",
        "ansible automation",
        "monitoring tools",
        "logging solutions",
        "testing frameworks",
        "code review tools",
        "ide plugins",
        "debugging tools"
    ]
}

# Flatten queries for easy access
ALL_QUERIES = [query for category in SEARCH_QUERIES.values() for query in category]

# Trending queries (higher probability)
TRENDING_QUERIES = [
    "machine learning tutorial",
    "python programming",
    "aws cloud services",
    "kubernetes deployment",
    "data science certification"
]


class SampleDataGenerator:
    """Generates realistic search query log data"""
    
    def __init__(self, seed: int = None):
        """Initialize generator with optional seed for reproducibility"""
        if seed:
            random.seed(seed)
    
    def generate_query_log(self, timestamp: datetime = None, user_id: str = None) -> Dict[str, Any]:
        """Generate a single search query log entry"""
        if timestamp is None:
            timestamp = datetime.utcnow()
        
        if user_id is None:
            user_id = f"user_{random.randint(1, 10000)}"
        
        # 30% chance of trending query
        if random.random() < 0.3:
            query = random.choice(TRENDING_QUERIES)
        else:
            query = random.choice(ALL_QUERIES)
        
        # Generate realistic metrics
        results_count = random.randint(0, 500)
        click_through = results_count > 0 and random.random() < 0.7
        
        return {
            "timestamp": timestamp.isoformat() + "Z",
            "user_id": user_id,
            "session_id": f"session_{random.randint(1, 50000)}",
            "query": query,
            "results_count": results_count,
            "click_through": click_through,
            "source": "sample_data_generator"
        }
    
    def generate_batch(self, count: int, start_time: datetime = None) -> List[Dict[str, Any]]:
        """Generate a batch of query logs"""
        if start_time is None:
            start_time = datetime.utcnow()
        
        logs = []
        for i in range(count):
            # Spread timestamps over the last hour
            timestamp = start_time - timedelta(seconds=random.randint(0, 3600))
            logs.append(self.generate_query_log(timestamp))
        
        return logs
    
    def generate_time_series(self, hours: int, queries_per_hour: int) -> List[Dict[str, Any]]:
        """Generate time series data over specified hours"""
        logs = []
        end_time = datetime.utcnow()
        
        for hour in range(hours):
            hour_start = end_time - timedelta(hours=hour)
            hour_logs = self.generate_batch(queries_per_hour, hour_start)
            logs.extend(hour_logs)
        
        return logs


class DataIngestionUtility:
    """Utility for ingesting sample data into the system"""
    
    def __init__(self, stream_name: str, region: str = "us-east-1", profile: str = None):
        """Initialize ingestion utility"""
        session_kwargs = {"region_name": region}
        if profile:
            session_kwargs["profile_name"] = profile
        
        session = boto3.Session(**session_kwargs)
        self.kinesis = session.client('kinesis')
        self.s3 = session.client('s3')
        self.stream_name = stream_name
    
    def ingest_to_kinesis(self, logs: List[Dict[str, Any]], batch_size: int = 500) -> Dict[str, int]:
        """Ingest logs to Kinesis Data Streams"""
        total = len(logs)
        success = 0
        failed = 0
        
        print(f"Ingesting {total} records to Kinesis stream '{self.stream_name}'...")
        
        for i in range(0, total, batch_size):
            batch = logs[i:i + batch_size]
            records = [
                {
                    "Data": json.dumps(log),
                    "PartitionKey": log["user_id"]
                }
                for log in batch
            ]
            
            try:
                response = self.kinesis.put_records(
                    StreamName=self.stream_name,
                    Records=records
                )
                
                success += len(records) - response.get('FailedRecordCount', 0)
                failed += response.get('FailedRecordCount', 0)
                
                print(f"Progress: {min(i + batch_size, total)}/{total} records processed")
                
                # Rate limiting to avoid throttling
                time.sleep(0.1)
                
            except Exception as e:
                print(f"Error ingesting batch: {e}")
                failed += len(records)
        
        return {"total": total, "success": success, "failed": failed}
    
    def ingest_to_s3(self, logs: List[Dict[str, Any]], bucket: str, prefix: str = "sample-data") -> Dict[str, Any]:
        """Ingest logs directly to S3 (for testing without Kinesis)"""
        timestamp = datetime.utcnow()
        key = f"{prefix}/year={timestamp.year}/month={timestamp.month:02d}/day={timestamp.day:02d}/hour={timestamp.hour:02d}/sample_{int(time.time())}.json"
        
        data = "\n".join([json.dumps(log) for log in logs])
        
        try:
            self.s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=data.encode('utf-8')
            )
            print(f"Uploaded {len(logs)} records to s3://{bucket}/{key}")
            return {"success": True, "key": key, "count": len(logs)}
        except Exception as e:
            print(f"Error uploading to S3: {e}")
            return {"success": False, "error": str(e)}


class DataValidationUtility:
    """Utility for validating data in the pipeline"""
    
    def __init__(self, region: str = "us-east-1", profile: str = None):
        """Initialize validation utility"""
        session_kwargs = {"region_name": region}
        if profile:
            session_kwargs["profile_name"] = profile
        
        session = boto3.Session(**session_kwargs)
        self.s3 = session.client('s3')
        self.dynamodb = session.client('dynamodb')
        self.kinesis = session.client('kinesis')
    
    def validate_kinesis_stream(self, stream_name: str) -> bool:
        """Validate Kinesis stream is active and accepting data"""
        try:
            response = self.kinesis.describe_stream(StreamName=stream_name)
            status = response['StreamDescription']['StreamStatus']
            
            if status == 'ACTIVE':
                print(f"✓ Kinesis stream '{stream_name}' is ACTIVE")
                return True
            else:
                print(f"✗ Kinesis stream '{stream_name}' status: {status}")
                return False
        except Exception as e:
            print(f"✗ Error validating Kinesis stream: {e}")
            return False
    
    def validate_s3_data(self, bucket: str, prefix: str = "") -> Dict[str, Any]:
        """Validate data exists in S3"""
        try:
            response = self.s3.list_objects_v2(
                Bucket=bucket,
                Prefix=prefix,
                MaxKeys=10
            )
            
            count = response.get('KeyCount', 0)
            if count > 0:
                print(f"✓ Found {count} objects in s3://{bucket}/{prefix}")
                return {"valid": True, "count": count}
            else:
                print(f"✗ No objects found in s3://{bucket}/{prefix}")
                return {"valid": False, "count": 0}
        except Exception as e:
            print(f"✗ Error validating S3 data: {e}")
            return {"valid": False, "error": str(e)}
    
    def validate_dynamodb_data(self, table_name: str) -> Dict[str, Any]:
        """Validate data exists in DynamoDB"""
        try:
            response = self.dynamodb.scan(
                TableName=table_name,
                Limit=10
            )
            
            count = response.get('Count', 0)
            if count > 0:
                print(f"✓ Found {count} items in DynamoDB table '{table_name}'")
                return {"valid": True, "count": count}
            else:
                print(f"✗ No items found in DynamoDB table '{table_name}'")
                return {"valid": False, "count": 0}
        except Exception as e:
            print(f"✗ Error validating DynamoDB data: {e}")
            return {"valid": False, "error": str(e)}


class CleanupUtility:
    """Utility for cleaning up test data"""
    
    def __init__(self, region: str = "us-east-1", profile: str = None):
        """Initialize cleanup utility"""
        session_kwargs = {"region_name": region}
        if profile:
            session_kwargs["profile_name"] = profile
        
        session = boto3.Session(**session_kwargs)
        self.s3 = session.client('s3')
        self.dynamodb = session.client('dynamodb')
    
    def cleanup_s3_prefix(self, bucket: str, prefix: str, dry_run: bool = True) -> Dict[str, int]:
        """Clean up S3 objects with given prefix"""
        deleted = 0
        
        try:
            paginator = self.s3.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=bucket, Prefix=prefix)
            
            for page in pages:
                if 'Contents' not in page:
                    continue
                
                objects = [{'Key': obj['Key']} for obj in page['Contents']]
                
                if dry_run:
                    print(f"[DRY RUN] Would delete {len(objects)} objects from s3://{bucket}/{prefix}")
                    deleted += len(objects)
                else:
                    response = self.s3.delete_objects(
                        Bucket=bucket,
                        Delete={'Objects': objects}
                    )
                    deleted += len(response.get('Deleted', []))
                    print(f"Deleted {len(response.get('Deleted', []))} objects from s3://{bucket}/{prefix}")
            
            return {"deleted": deleted, "dry_run": dry_run}
        except Exception as e:
            print(f"Error cleaning up S3: {e}")
            return {"deleted": 0, "error": str(e)}
    
    def cleanup_dynamodb_test_data(self, table_name: str, dry_run: bool = True) -> Dict[str, int]:
        """Clean up test data from DynamoDB (items with source='sample_data_generator')"""
        deleted = 0
        
        try:
            # Scan for test data
            response = self.dynamodb.scan(
                TableName=table_name,
                FilterExpression="contains(#src, :test_source)",
                ExpressionAttributeNames={"#src": "source"},
                ExpressionAttributeValues={":test_source": {"S": "sample_data_generator"}}
            )
            
            items = response.get('Items', [])
            
            if dry_run:
                print(f"[DRY RUN] Would delete {len(items)} test items from DynamoDB table '{table_name}'")
                return {"deleted": len(items), "dry_run": dry_run}
            
            for item in items:
                # Extract key
                key = {"date": item["date"]}
                self.dynamodb.delete_item(TableName=table_name, Key=key)
                deleted += 1
            
            print(f"Deleted {deleted} test items from DynamoDB table '{table_name}'")
            return {"deleted": deleted, "dry_run": dry_run}
        except Exception as e:
            print(f"Error cleaning up DynamoDB: {e}")
            return {"deleted": 0, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(
        description="Generate and ingest sample search query data for testing"
    )
    
    parser.add_argument(
        "--env",
        required=True,
        choices=["dev", "staging", "prod"],
        help="Environment to target"
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1000,
        help="Number of sample records to generate (default: 1000)"
    )
    parser.add_argument(
        "--hours",
        type=int,
        help="Generate time series data over N hours"
    )
    parser.add_argument(
        "--queries-per-hour",
        type=int,
        default=100,
        help="Queries per hour for time series generation (default: 100)"
    )
    parser.add_argument(
        "--stream-name",
        help="Kinesis stream name (default: auto-detect from env)"
    )
    parser.add_argument(
        "--s3-bucket",
        help="S3 bucket for direct upload (bypasses Kinesis)"
    )
    parser.add_argument(
        "--region",
        default="us-east-1",
        help="AWS region (default: us-east-1)"
    )
    parser.add_argument(
        "--profile",
        help="AWS profile to use"
    )
    parser.add_argument(
        "--seed",
        type=int,
        help="Random seed for reproducible data generation"
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate data ingestion"
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Clean up test data"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run for cleanup operations"
    )
    
    args = parser.parse_args()
    
    # Auto-detect stream name if not provided
    if not args.stream_name and not args.s3_bucket and not args.cleanup:
        args.stream_name = f"OpenSearchTrendingQueries-{args.env}-SearchQueryStream"
    
    # Cleanup mode
    if args.cleanup:
        print(f"\n{'='*60}")
        print(f"CLEANUP MODE - Environment: {args.env}")
        print(f"{'='*60}\n")
        
        cleanup = CleanupUtility(region=args.region, profile=args.profile)
        
        if args.s3_bucket:
            result = cleanup.cleanup_s3_prefix(
                bucket=args.s3_bucket,
                prefix="sample-data",
                dry_run=args.dry_run
            )
            print(f"\nS3 Cleanup Result: {result}")
        
        # Add DynamoDB cleanup if table name provided
        print("\nCleanup complete!")
        return
    
    # Generate data
    print(f"\n{'='*60}")
    print(f"SAMPLE DATA GENERATION - Environment: {args.env}")
    print(f"{'='*60}\n")
    
    generator = SampleDataGenerator(seed=args.seed)
    
    if args.hours:
        print(f"Generating time series data: {args.hours} hours, {args.queries_per_hour} queries/hour")
        logs = generator.generate_time_series(args.hours, args.queries_per_hour)
    else:
        print(f"Generating {args.count} sample records...")
        logs = generator.generate_batch(args.count)
    
    print(f"Generated {len(logs)} sample query logs\n")
    
    # Ingest data
    ingestion = DataIngestionUtility(
        stream_name=args.stream_name or "",
        region=args.region,
        profile=args.profile
    )
    
    if args.s3_bucket:
        print(f"Ingesting to S3 bucket: {args.s3_bucket}")
        result = ingestion.ingest_to_s3(logs, args.s3_bucket)
        print(f"\nIngestion Result: {result}")
    elif args.stream_name:
        result = ingestion.ingest_to_kinesis(logs)
        print(f"\nIngestion Result: {result}")
    else:
        print("Error: Must specify either --stream-name or --s3-bucket")
        sys.exit(1)
    
    # Validation
    if args.validate:
        print(f"\n{'='*60}")
        print("VALIDATION")
        print(f"{'='*60}\n")
        
        validator = DataValidationUtility(region=args.region, profile=args.profile)
        
        if args.stream_name:
            validator.validate_kinesis_stream(args.stream_name)
        
        if args.s3_bucket:
            validator.validate_s3_data(args.s3_bucket, "sample-data")
    
    print("\nSample data generation complete!")


if __name__ == "__main__":
    main()
