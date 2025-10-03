#!/usr/bin/env python3
"""
Integration Test Runner for OpenSearch Trending Queries
Runs end-to-end tests for the data pipeline and API
"""
import argparse
import boto3
import json
import time
import sys
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from botocore.exceptions import ClientError


class IntegrationTestRunner:
    """Runs integration tests for the deployed infrastructure"""
    
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
        self.kinesis_client = self.session.client("kinesis")
        self.dynamodb_client = self.session.client("dynamodb")
        self.apigateway_client = self.session.client("apigateway")
        self.lambda_client = self.session.client("lambda")
        self.sfn_client = self.session.client("stepfunctions")
        self.s3_client = self.session.client("s3")
        
        self.test_results = []
        self.stack_outputs = {}
    
    def run_all_tests(self) -> bool:
        """Run all integration tests"""
        print(f"Running integration tests for {self.environment} environment...\n")
        
        # Load stack outputs
        if not self._load_stack_outputs():
            print("Error: Could not load stack outputs")
            return False
        
        # Run test suites
        self._test_data_ingestion()
        self._test_api_endpoints()
        self._test_lambda_functions()
        self._test_step_functions()
        self._test_data_quality()
        
        # Print results
        self._print_results()
        
        # Return overall status
        return all(result["success"] for result in self.test_results)
    
    def _load_stack_outputs(self) -> bool:
        """Load CloudFormation stack outputs"""
        try:
            response = self.cfn_client.describe_stacks(StackName=self.stack_name)
            stacks = response.get("Stacks", [])
            
            if not stacks:
                return False
            
            for output in stacks[0].get("Outputs", []):
                self.stack_outputs[output["OutputKey"]] = output["OutputValue"]
            
            print(f"Loaded {len(self.stack_outputs)} stack outputs")
            return True
        except ClientError as e:
            print(f"Error loading stack outputs: {e}")
            return False
    
    def _test_data_ingestion(self) -> None:
        """Test data ingestion through Kinesis"""
        print("\n=== Testing Data Ingestion ===")
        
        stream_name = self.stack_outputs.get("KinesisStreamName")
        if not stream_name:
            self._add_result("Data Ingestion", False, "Stream name not found")
            return
        
        # Test 1: Send test record to Kinesis
        test_record = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "user_id": "test_user_123",
            "session_id": "test_session_456",
            "query": "integration test query",
            "results_count": 100,
            "click_through": True,
            "source": "integration_test"
        }
        
        try:
            response = self.kinesis_client.put_record(
                StreamName=stream_name,
                Data=json.dumps(test_record),
                PartitionKey=test_record["user_id"]
            )
            
            shard_id = response.get("ShardId")
            sequence_number = response.get("SequenceNumber")
            
            self._add_result(
                "Kinesis Put Record",
                True,
                f"Shard: {shard_id}, Sequence: {sequence_number[:20]}..."
            )
        except ClientError as e:
            self._add_result("Kinesis Put Record", False, str(e))
        
        # Test 2: Verify stream is active
        try:
            response = self.kinesis_client.describe_stream(StreamName=stream_name)
            status = response["StreamDescription"]["StreamStatus"]
            
            self._add_result(
                "Kinesis Stream Status",
                status == "ACTIVE",
                f"Status: {status}"
            )
        except ClientError as e:
            self._add_result("Kinesis Stream Status", False, str(e))
    
    def _test_api_endpoints(self) -> None:
        """Test API Gateway endpoints"""
        print("\n=== Testing API Endpoints ===")
        
        api_url = self.stack_outputs.get("ApiUrl")
        if not api_url:
            self._add_result("API Endpoints", False, "API URL not found")
            return
        
        # Test 1: GET /trending-queries
        try:
            import urllib.request
            import urllib.error
            
            url = f"{api_url}trending-queries"
            req = urllib.request.Request(url, method="GET")
            
            try:
                with urllib.request.urlopen(req, timeout=10) as response:
                    status_code = response.status
                    data = json.loads(response.read().decode())
                    
                    self._add_result(
                        "GET /trending-queries",
                        status_code == 200,
                        f"Status: {status_code}, Items: {len(data.get('trending_queries', []))}"
                    )
            except urllib.error.HTTPError as e:
                # 404 is acceptable if no data exists yet
                if e.code == 404:
                    self._add_result(
                        "GET /trending-queries",
                        True,
                        "No data yet (404 expected)"
                    )
                else:
                    self._add_result(
                        "GET /trending-queries",
                        False,
                        f"HTTP {e.code}: {e.reason}"
                    )
        except Exception as e:
            self._add_result("GET /trending-queries", False, str(e))
        
        # Test 2: GET /trending-queries/{date}
        try:
            test_date = datetime.utcnow().strftime("%Y-%m-%d")
            url = f"{api_url}trending-queries/{test_date}"
            req = urllib.request.Request(url, method="GET")
            
            try:
                with urllib.request.urlopen(req, timeout=10) as response:
                    status_code = response.status
                    data = json.loads(response.read().decode())
                    
                    self._add_result(
                        f"GET /trending-queries/{test_date}",
                        status_code == 200,
                        f"Status: {status_code}"
                    )
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    self._add_result(
                        f"GET /trending-queries/{test_date}",
                        True,
                        "No data for date (404 expected)"
                    )
                else:
                    self._add_result(
                        f"GET /trending-queries/{test_date}",
                        False,
                        f"HTTP {e.code}: {e.reason}"
                    )
        except Exception as e:
            self._add_result(f"GET /trending-queries/{test_date}", False, str(e))
    
    def _test_lambda_functions(self) -> None:
        """Test Lambda functions"""
        print("\n=== Testing Lambda Functions ===")
        
        lambda_functions = [
            ("GetTrendingQueriesFunctionName", "Get Trending Queries"),
            ("GetTrendingQueriesByDateFunctionName", "Get Trending Queries By Date"),
            ("BedrockClassificationFunctionName", "Bedrock Classification"),
            ("LogCompressionFunctionName", "Log Compression")
        ]
        
        for output_key, display_name in lambda_functions:
            function_name = self.stack_outputs.get(output_key)
            if not function_name:
                continue
            
            try:
                # Get function configuration
                response = self.lambda_client.get_function(FunctionName=function_name)
                config = response.get("Configuration", {})
                
                state = config.get("State")
                last_update_status = config.get("LastUpdateStatus")
                
                success = state == "Active" and last_update_status == "Successful"
                
                self._add_result(
                    f"Lambda: {display_name}",
                    success,
                    f"State: {state}, Update: {last_update_status}"
                )
            except ClientError as e:
                self._add_result(f"Lambda: {display_name}", False, str(e))
    
    def _test_step_functions(self) -> None:
        """Test Step Functions state machine"""
        print("\n=== Testing Step Functions ===")
        
        state_machine_arn = self.stack_outputs.get("StepFunctionArn")
        if not state_machine_arn:
            self._add_result("Step Functions", False, "State machine ARN not found")
            return
        
        # Test 1: Verify state machine exists and is active
        try:
            response = self.sfn_client.describe_state_machine(
                stateMachineArn=state_machine_arn
            )
            
            status = response.get("status")
            name = response.get("name")
            
            self._add_result(
                "Step Functions State Machine",
                status == "ACTIVE",
                f"Name: {name}, Status: {status}"
            )
        except ClientError as e:
            self._add_result("Step Functions State Machine", False, str(e))
        
        # Test 2: Check recent executions
        try:
            response = self.sfn_client.list_executions(
                stateMachineArn=state_machine_arn,
                maxResults=10
            )
            
            executions = response.get("executions", [])
            
            if executions:
                latest = executions[0]
                status = latest.get("status")
                start_date = latest.get("startDate")
                
                self._add_result(
                    "Step Functions Recent Execution",
                    True,
                    f"Status: {status}, Started: {start_date}"
                )
            else:
                self._add_result(
                    "Step Functions Recent Execution",
                    True,
                    "No executions yet (expected for new deployment)"
                )
        except ClientError as e:
            self._add_result("Step Functions Recent Execution", False, str(e))
    
    def _test_data_quality(self) -> None:
        """Test data quality in DynamoDB"""
        print("\n=== Testing Data Quality ===")
        
        table_name = self.stack_outputs.get("TrendingQueriesTableName")
        if not table_name:
            self._add_result("Data Quality", False, "Table name not found")
            return
        
        # Test 1: Scan table for recent data
        try:
            response = self.dynamodb_client.scan(
                TableName=table_name,
                Limit=10
            )
            
            items = response.get("Items", [])
            count = response.get("Count", 0)
            
            if count > 0:
                # Validate data structure
                sample_item = items[0]
                has_date = "date" in sample_item
                has_queries = "trending_queries" in sample_item
                
                self._add_result(
                    "DynamoDB Data Quality",
                    has_date and has_queries,
                    f"Items: {count}, Valid structure: {has_date and has_queries}"
                )
            else:
                self._add_result(
                    "DynamoDB Data Quality",
                    True,
                    "No data yet (expected for new deployment)"
                )
        except ClientError as e:
            self._add_result("DynamoDB Data Quality", False, str(e))
        
        # Test 2: Check S3 buckets for data
        raw_bucket = self.stack_outputs.get("RawDataBucketName")
        if raw_bucket:
            try:
                response = self.s3_client.list_objects_v2(
                    Bucket=raw_bucket,
                    MaxKeys=10
                )
                
                object_count = response.get("KeyCount", 0)
                
                self._add_result(
                    "S3 Raw Data",
                    True,
                    f"Objects: {object_count}"
                )
            except ClientError as e:
                self._add_result("S3 Raw Data", False, str(e))
    
    def _add_result(self, test_name: str, success: bool, details: str) -> None:
        """Add test result"""
        self.test_results.append({
            "test": test_name,
            "success": success,
            "details": details
        })
    
    def _print_results(self) -> None:
        """Print test results"""
        print("\n" + "="*80)
        print("INTEGRATION TEST RESULTS")
        print("="*80 + "\n")
        
        for result in self.test_results:
            status = "✓ PASS" if result["success"] else "✗ FAIL"
            print(f"{status:8} | {result['test']:40} | {result['details']}")
        
        print("\n" + "="*80)
        
        passed = sum(1 for r in self.test_results if r["success"])
        total = len(self.test_results)
        
        print(f"Results: {passed}/{total} tests passed")
        print("="*80 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Run integration tests for OpenSearch Trending Queries"
    )
    parser.add_argument(
        "--env",
        required=True,
        choices=["dev", "staging", "prod"],
        help="Environment to test"
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
        runner = IntegrationTestRunner(
            environment=args.env,
            region=args.region,
            profile=args.profile
        )
        
        success = runner.run_all_tests()
        sys.exit(0 if success else 1)
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
