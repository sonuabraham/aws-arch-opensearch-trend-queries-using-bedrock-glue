#!/usr/bin/env python3
"""
Post-deployment validation script
Validates that all components are properly deployed and functional
"""
import argparse
import boto3
import json
import sys
from typing import Dict, List, Any, Optional
from botocore.exceptions import ClientError


class DeploymentValidator:
    """Validates deployed infrastructure components"""
    
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
        self.kinesis_client = self.session.client("kinesis")
        self.glue_client = self.session.client("glue")
        self.sfn_client = self.session.client("stepfunctions")
        self.apigateway_client = self.session.client("apigateway")
        self.lambda_client = self.session.client("lambda")
        
        self.validation_results = []
    
    def validate_all(self) -> bool:
        """Run all validation checks"""
        print(f"Validating deployment for {self.environment} environment...\n")
        
        # Get stack outputs
        outputs = self._get_stack_outputs()
        if not outputs:
            self._add_result("Stack Outputs", False, "Could not retrieve stack outputs")
            return False
        
        self._add_result("Stack Outputs", True, f"Retrieved {len(outputs)} outputs")
        
        # Run validation checks
        self._validate_s3_buckets(outputs)
        self._validate_dynamodb_table(outputs)
        self._validate_kinesis_stream(outputs)
        self._validate_glue_resources(outputs)
        self._validate_step_functions(outputs)
        self._validate_api_gateway(outputs)
        self._validate_lambda_functions(outputs)
        
        # Print results
        self._print_results()
        
        # Return overall status
        return all(result["success"] for result in self.validation_results)
    
    def _get_stack_outputs(self) -> Dict[str, str]:
        """Get CloudFormation stack outputs"""
        try:
            response = self.cfn_client.describe_stacks(StackName=self.stack_name)
            stacks = response.get("Stacks", [])
            
            if not stacks:
                return {}
            
            outputs = {}
            for output in stacks[0].get("Outputs", []):
                outputs[output["OutputKey"]] = output["OutputValue"]
            
            return outputs
        except ClientError as e:
            print(f"Error getting stack outputs: {e}")
            return {}
    
    def _validate_s3_buckets(self, outputs: Dict[str, str]) -> None:
        """Validate S3 buckets exist and are configured correctly"""
        bucket_keys = [
            "RawDataBucketName",
            "ProcessedDataBucketName",
            "QueryResultsBucketName"
        ]
        
        for key in bucket_keys:
            bucket_name = outputs.get(key)
            if not bucket_name:
                self._add_result(f"S3 Bucket ({key})", False, "Output not found")
                continue
            
            try:
                # Check bucket exists
                self.s3_client.head_bucket(Bucket=bucket_name)
                
                # Check encryption
                encryption = self.s3_client.get_bucket_encryption(Bucket=bucket_name)
                has_encryption = bool(encryption.get("ServerSideEncryptionConfiguration"))
                
                # Check versioning
                versioning = self.s3_client.get_bucket_versioning(Bucket=bucket_name)
                is_versioned = versioning.get("Status") == "Enabled"
                
                details = f"Encryption: {has_encryption}, Versioning: {is_versioned}"
                self._add_result(f"S3 Bucket ({bucket_name})", True, details)
                
            except ClientError as e:
                self._add_result(f"S3 Bucket ({bucket_name})", False, str(e))
    
    def _validate_dynamodb_table(self, outputs: Dict[str, str]) -> None:
        """Validate DynamoDB table exists and is configured correctly"""
        table_name = outputs.get("TrendingQueriesTableName")
        if not table_name:
            self._add_result("DynamoDB Table", False, "Output not found")
            return
        
        try:
            response = self.dynamodb_client.describe_table(TableName=table_name)
            table = response.get("Table", {})
            
            status = table.get("TableStatus")
            billing_mode = table.get("BillingModeSummary", {}).get("BillingMode", "PROVISIONED")
            has_ttl = table.get("TimeToLiveDescription", {}).get("TimeToLiveStatus") == "ENABLED"
            
            details = f"Status: {status}, Billing: {billing_mode}, TTL: {has_ttl}"
            success = status == "ACTIVE"
            
            self._add_result(f"DynamoDB Table ({table_name})", success, details)
            
        except ClientError as e:
            self._add_result(f"DynamoDB Table ({table_name})", False, str(e))
    
    def _validate_kinesis_stream(self, outputs: Dict[str, str]) -> None:
        """Validate Kinesis stream exists and is active"""
        stream_name = outputs.get("KinesisStreamName")
        if not stream_name:
            self._add_result("Kinesis Stream", False, "Output not found")
            return
        
        try:
            response = self.kinesis_client.describe_stream(StreamName=stream_name)
            stream = response.get("StreamDescription", {})
            
            status = stream.get("StreamStatus")
            shard_count = len(stream.get("Shards", []))
            retention_hours = stream.get("RetentionPeriodHours")
            
            details = f"Status: {status}, Shards: {shard_count}, Retention: {retention_hours}h"
            success = status == "ACTIVE"
            
            self._add_result(f"Kinesis Stream ({stream_name})", success, details)
            
        except ClientError as e:
            self._add_result(f"Kinesis Stream ({stream_name})", False, str(e))
    
    def _validate_glue_resources(self, outputs: Dict[str, str]) -> None:
        """Validate Glue database, crawler, and jobs"""
        database_name = outputs.get("GlueDatabaseName")
        
        # Validate database
        if database_name:
            try:
                self.glue_client.get_database(Name=database_name)
                self._add_result(f"Glue Database ({database_name})", True, "Exists")
            except ClientError as e:
                self._add_result(f"Glue Database ({database_name})", False, str(e))
        
        # Validate crawler
        crawler_name = outputs.get("GlueCrawlerName")
        if crawler_name:
            try:
                response = self.glue_client.get_crawler(Name=crawler_name)
                state = response.get("Crawler", {}).get("State")
                self._add_result(f"Glue Crawler ({crawler_name})", True, f"State: {state}")
            except ClientError as e:
                self._add_result(f"Glue Crawler ({crawler_name})", False, str(e))
    
    def _validate_step_functions(self, outputs: Dict[str, str]) -> None:
        """Validate Step Functions state machine"""
        state_machine_arn = outputs.get("StepFunctionArn")
        if not state_machine_arn:
            self._add_result("Step Functions", False, "Output not found")
            return
        
        try:
            response = self.sfn_client.describe_state_machine(
                stateMachineArn=state_machine_arn
            )
            
            status = response.get("status")
            name = response.get("name")
            
            self._add_result(f"Step Functions ({name})", status == "ACTIVE", f"Status: {status}")
            
        except ClientError as e:
            self._add_result("Step Functions", False, str(e))
    
    def _validate_api_gateway(self, outputs: Dict[str, str]) -> None:
        """Validate API Gateway"""
        api_url = outputs.get("ApiUrl")
        api_id = outputs.get("ApiId")
        
        if not api_id:
            self._add_result("API Gateway", False, "Output not found")
            return
        
        try:
            response = self.apigateway_client.get_rest_api(restApiId=api_id)
            name = response.get("name")
            
            self._add_result(f"API Gateway ({name})", True, f"URL: {api_url}")
            
        except ClientError as e:
            self._add_result("API Gateway", False, str(e))
    
    def _validate_lambda_functions(self, outputs: Dict[str, str]) -> None:
        """Validate Lambda functions"""
        lambda_keys = [
            "GetTrendingQueriesFunctionName",
            "GetTrendingQueriesByDateFunctionName",
            "BedrockClassificationFunctionName",
            "LogCompressionFunctionName"
        ]
        
        for key in lambda_keys:
            function_name = outputs.get(key)
            if not function_name:
                continue
            
            try:
                response = self.lambda_client.get_function(FunctionName=function_name)
                config = response.get("Configuration", {})
                
                state = config.get("State")
                runtime = config.get("Runtime")
                memory = config.get("MemorySize")
                
                details = f"State: {state}, Runtime: {runtime}, Memory: {memory}MB"
                success = state == "Active"
                
                self._add_result(f"Lambda ({function_name})", success, details)
                
            except ClientError as e:
                self._add_result(f"Lambda ({function_name})", False, str(e))
    
    def _add_result(self, component: str, success: bool, details: str) -> None:
        """Add validation result"""
        self.validation_results.append({
            "component": component,
            "success": success,
            "details": details
        })
    
    def _print_results(self) -> None:
        """Print validation results"""
        print("\n" + "="*80)
        print("VALIDATION RESULTS")
        print("="*80 + "\n")
        
        for result in self.validation_results:
            status = "✓ PASS" if result["success"] else "✗ FAIL"
            print(f"{status:8} | {result['component']:40} | {result['details']}")
        
        print("\n" + "="*80)
        
        passed = sum(1 for r in self.validation_results if r["success"])
        total = len(self.validation_results)
        
        print(f"Results: {passed}/{total} checks passed")
        print("="*80 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Validate OpenSearch Trending Queries deployment"
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
        validator = DeploymentValidator(
            environment=args.env,
            region=args.region,
            profile=args.profile
        )
        
        success = validator.validate_all()
        sys.exit(0 if success else 1)
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
