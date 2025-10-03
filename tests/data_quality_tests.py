#!/usr/bin/env python3
"""
Data Quality Validation Tests
Validates data integrity and quality throughout the pipeline
"""
import argparse
import boto3
import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from botocore.exceptions import ClientError


class DataQualityValidator:
    """Validates data quality in the pipeline"""
    
    def __init__(self, environment: str, region: str = "us-east-1", profile: Optional[str] = None):
        self.environment = environment
        self.region = region
        self.stack_name = f"OpenSearchTrendingQueries-{environment}"
        
        # Initialize AWS session
        session_kwargs = {"region_name": region}
        if profile:
            session_kwargs["profile_name"] = profile
        
        self.session = boto3.Session(**session_kwargs)
        self.cfn_client = self.session.client("cloudformation")
        self.s3_client = self.session.client("s3")
        self.dynamodb_client = self.session.client("dynamodb")
        self.glue_client = self.session.client("glue")
        self.athena_client = self.session.client("athena")
        
        self.stack_outputs = {}
        self.validation_results = []
    
    def run_all_validations(self) -> bool:
        """Run all data quality validations"""
        print(f"Running data quality validations for {self.environment} environment...\n")
        
        # Load stack outputs
        if not self._load_stack_outputs():
            print("Error: Could not load stack outputs")
            return False
        
        # Run validations
        self._validate_s3_data_structure()
        self._validate_dynamodb_data()
        self._validate_glue_catalog()
        self._validate_data_freshness()
        
        # Print results
        self._print_results()
        
        return all(result["success"] for result in self.validation_results)
    
    def _load_stack_outputs(self) -> bool:
        """Load CloudFormation stack outputs"""
        try:
            response = self.cfn_client.describe_stacks(StackName=self.stack_name)
            stacks = response.get("Stacks", [])
            
            if not stacks:
                return False
            
            for output in stacks[0].get("Outputs", []):
                self.stack_outputs[output["OutputKey"]] = output["OutputValue"]
            
            return True
        except ClientError as e:
            print(f"Error loading stack outputs: {e}")
            return False
    
    def _validate_s3_data_structure(self) -> None:
        """Validate S3 data structure and partitioning"""
        print("\n=== Validating S3 Data Structure ===")
        
        raw_bucket = self.stack_outputs.get("RawDataBucketName")
        processed_bucket = self.stack_outputs.get("ProcessedDataBucketName")
        
        # Validate raw data bucket
        if raw_bucket:
            try:
                # Check for date partitioning (year/month/day/hour)
                response = self.s3_client.list_objects_v2(
                    Bucket=raw_bucket,
                    Delimiter="/",
                    MaxKeys=10
                )
                
                prefixes = [p["Prefix"] for p in response.get("CommonPrefixes", [])]
                
                # Check if partitions follow expected pattern
                has_partitions = any(p.startswith("year=") for p in prefixes)
                
                self._add_result(
                    "S3 Raw Data Partitioning",
                    True,
                    f"Partitions found: {has_partitions}, Prefixes: {len(prefixes)}"
                )
                
                # Validate data files
                if has_partitions:
                    # Get sample file
                    response = self.s3_client.list_objects_v2(
                        Bucket=raw_bucket,
                        MaxKeys=1
                    )
                    
                    if response.get("Contents"):
                        obj = response["Contents"][0]
                        key = obj["Key"]
                        size = obj["Size"]
                        
                        self._add_result(
                            "S3 Raw Data Files",
                            size > 0,
                            f"Sample file: {key}, Size: {size} bytes"
                        )
                
            except ClientError as e:
                self._add_result("S3 Raw Data Structure", False, str(e))
        
        # Validate processed data bucket
        if processed_bucket:
            try:
                response = self.s3_client.list_objects_v2(
                    Bucket=processed_bucket,
                    MaxKeys=10
                )
                
                object_count = response.get("KeyCount", 0)
                
                self._add_result(
                    "S3 Processed Data",
                    True,
                    f"Objects: {object_count}"
                )
                
            except ClientError as e:
                self._add_result("S3 Processed Data", False, str(e))
    
    def _validate_dynamodb_data(self) -> None:
        """Validate DynamoDB data structure and content"""
        print("\n=== Validating DynamoDB Data ===")
        
        table_name = self.stack_outputs.get("TrendingQueriesTableName")
        if not table_name:
            self._add_result("DynamoDB Data", False, "Table name not found")
            return
        
        try:
            # Scan for recent data
            response = self.dynamodb_client.scan(
                TableName=table_name,
                Limit=10
            )
            
            items = response.get("Items", [])
            
            if not items:
                self._add_result(
                    "DynamoDB Data Presence",
                    True,
                    "No data yet (expected for new deployment)"
                )
                return
            
            # Validate data structure
            validation_errors = []
            
            for item in items:
                # Check required fields
                if "date" not in item:
                    validation_errors.append("Missing 'date' field")
                
                if "trending_queries" not in item:
                    validation_errors.append("Missing 'trending_queries' field")
                else:
                    # Validate trending_queries structure
                    queries = item["trending_queries"]
                    if "L" in queries:  # DynamoDB list format
                        query_list = queries["L"]
                        
                        for query in query_list:
                            if "M" in query:  # DynamoDB map format
                                query_map = query["M"]
                                
                                # Check required query fields
                                required_fields = ["query", "rank", "count"]
                                for field in required_fields:
                                    if field not in query_map:
                                        validation_errors.append(f"Missing '{field}' in query")
            
            success = len(validation_errors) == 0
            details = f"Items: {len(items)}, Errors: {len(validation_errors)}"
            if validation_errors:
                details += f" - {validation_errors[:3]}"
            
            self._add_result("DynamoDB Data Structure", success, details)
            
            # Validate data freshness
            if items:
                latest_date = None
                for item in items:
                    if "date" in item and "S" in item["date"]:
                        date_str = item["date"]["S"]
                        try:
                            date = datetime.strptime(date_str, "%Y-%m-%d")
                            if latest_date is None or date > latest_date:
                                latest_date = date
                        except ValueError:
                            pass
                
                if latest_date:
                    days_old = (datetime.utcnow() - latest_date).days
                    is_fresh = days_old <= 7
                    
                    self._add_result(
                        "DynamoDB Data Freshness",
                        is_fresh,
                        f"Latest date: {latest_date.strftime('%Y-%m-%d')}, Age: {days_old} days"
                    )
            
        except ClientError as e:
            self._add_result("DynamoDB Data", False, str(e))
    
    def _validate_glue_catalog(self) -> None:
        """Validate Glue Data Catalog"""
        print("\n=== Validating Glue Catalog ===")
        
        database_name = self.stack_outputs.get("GlueDatabaseName")
        if not database_name:
            self._add_result("Glue Catalog", False, "Database name not found")
            return
        
        try:
            # Get database
            self.glue_client.get_database(Name=database_name)
            
            # Get tables
            response = self.glue_client.get_tables(DatabaseName=database_name)
            tables = response.get("TableList", [])
            
            self._add_result(
                "Glue Catalog Tables",
                True,
                f"Tables: {len(tables)}"
            )
            
            # Validate table schemas
            for table in tables:
                table_name = table["Name"]
                columns = table.get("StorageDescriptor", {}).get("Columns", [])
                
                has_columns = len(columns) > 0
                
                self._add_result(
                    f"Glue Table Schema: {table_name}",
                    has_columns,
                    f"Columns: {len(columns)}"
                )
            
        except ClientError as e:
            self._add_result("Glue Catalog", False, str(e))
    
    def _validate_data_freshness(self) -> None:
        """Validate data freshness across the pipeline"""
        print("\n=== Validating Data Freshness ===")
        
        raw_bucket = self.stack_outputs.get("RawDataBucketName")
        
        if raw_bucket:
            try:
                # Get most recent object
                response = self.s3_client.list_objects_v2(
                    Bucket=raw_bucket,
                    MaxKeys=100
                )
                
                objects = response.get("Contents", [])
                
                if objects:
                    # Find most recent object
                    latest_object = max(objects, key=lambda x: x["LastModified"])
                    last_modified = latest_object["LastModified"]
                    
                    # Check if data is recent (within last 24 hours)
                    age_hours = (datetime.now(last_modified.tzinfo) - last_modified).total_seconds() / 3600
                    is_fresh = age_hours <= 24
                    
                    self._add_result(
                        "S3 Data Freshness",
                        is_fresh,
                        f"Latest object: {age_hours:.1f} hours old"
                    )
                else:
                    self._add_result(
                        "S3 Data Freshness",
                        True,
                        "No data yet (expected for new deployment)"
                    )
                
            except ClientError as e:
                self._add_result("S3 Data Freshness", False, str(e))
    
    def _add_result(self, validation: str, success: bool, details: str) -> None:
        """Add validation result"""
        self.validation_results.append({
            "validation": validation,
            "success": success,
            "details": details
        })
    
    def _print_results(self) -> None:
        """Print validation results"""
        print("\n" + "="*80)
        print("DATA QUALITY VALIDATION RESULTS")
        print("="*80 + "\n")
        
        for result in self.validation_results:
            status = "✓ PASS" if result["success"] else "✗ FAIL"
            print(f"{status:8} | {result['validation']:40} | {result['details']}")
        
        print("\n" + "="*80)
        
        passed = sum(1 for r in self.validation_results if r["success"])
        total = len(self.validation_results)
        
        print(f"Results: {passed}/{total} validations passed")
        print("="*80 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Validate data quality for OpenSearch Trending Queries"
    )
    parser.add_argument(
        "--env",
        required=True,
        choices=["dev", "staging", "prod"],
        help="Environment to validate"
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
    
    args = parser.parse_args()
    
    try:
        validator = DataQualityValidator(
            environment=args.env,
            region=args.region,
            profile=args.profile
        )
        
        success = validator.run_all_validations()
        import sys
        sys.exit(0 if success else 1)
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import sys
        sys.exit(1)


if __name__ == "__main__":
    main()
