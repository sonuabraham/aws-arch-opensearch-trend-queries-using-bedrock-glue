#!/usr/bin/env python3
"""
Performance and Load Testing for OpenSearch Trending Queries
Tests system performance under various load conditions
"""
import argparse
import boto3
import json
import time
import random
import concurrent.futures
from typing import Dict, List, Optional, Any
from datetime import datetime
from statistics import mean, median, stdev
from botocore.exceptions import ClientError


class PerformanceTestRunner:
    """Runs performance and load tests"""
    
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
        
        self.stack_outputs = {}
        self.test_results = {}
    
    def run_all_tests(self, duration_seconds: int = 60, requests_per_second: int = 10) -> None:
        """Run all performance tests"""
        print(f"Running performance tests for {self.environment} environment...")
        print(f"Duration: {duration_seconds}s, Target RPS: {requests_per_second}\n")
        
        # Load stack outputs
        if not self._load_stack_outputs():
            print("Error: Could not load stack outputs")
            return
        
        # Run test suites
        self._test_kinesis_throughput(duration_seconds, requests_per_second)
        self._test_api_latency(duration_seconds, requests_per_second)
        
        # Print results
        self._print_results()
    
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
    
    def _test_kinesis_throughput(self, duration: int, target_rps: int) -> None:
        """Test Kinesis ingestion throughput"""
        print("\n=== Testing Kinesis Throughput ===")
        
        stream_name = self.stack_outputs.get("KinesisStreamName")
        if not stream_name:
            print("Stream name not found")
            return
        
        # Generate test queries
        test_queries = [
            "machine learning tutorial",
            "python programming",
            "aws cloud services",
            "data science course",
            "web development",
            "artificial intelligence",
            "database design",
            "api development",
            "mobile app development",
            "cybersecurity basics"
        ]
        
        latencies = []
        errors = 0
        successful = 0
        
        start_time = time.time()
        end_time = start_time + duration
        
        print(f"Sending records to Kinesis for {duration} seconds...")
        
        while time.time() < end_time:
            batch_start = time.time()
            
            # Send batch of records
            for _ in range(target_rps):
                record = {
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "user_id": f"user_{random.randint(1, 10000)}",
                    "session_id": f"session_{random.randint(1, 50000)}",
                    "query": random.choice(test_queries),
                    "results_count": random.randint(0, 500),
                    "click_through": random.choice([True, False]),
                    "source": "performance_test"
                }
                
                record_start = time.time()
                try:
                    self.kinesis_client.put_record(
                        StreamName=stream_name,
                        Data=json.dumps(record),
                        PartitionKey=record["user_id"]
                    )
                    latencies.append((time.time() - record_start) * 1000)  # ms
                    successful += 1
                except ClientError as e:
                    errors += 1
            
            # Sleep to maintain target RPS
            elapsed = time.time() - batch_start
            sleep_time = max(0, 1.0 - elapsed)
            time.sleep(sleep_time)
        
        total_time = time.time() - start_time
        actual_rps = successful / total_time
        
        self.test_results["kinesis_throughput"] = {
            "total_records": successful,
            "errors": errors,
            "duration_seconds": total_time,
            "actual_rps": actual_rps,
            "target_rps": target_rps,
            "avg_latency_ms": mean(latencies) if latencies else 0,
            "median_latency_ms": median(latencies) if latencies else 0,
            "p95_latency_ms": self._percentile(latencies, 95) if latencies else 0,
            "p99_latency_ms": self._percentile(latencies, 99) if latencies else 0,
            "max_latency_ms": max(latencies) if latencies else 0
        }
        
        print(f"Completed: {successful} records, {errors} errors")
        print(f"Actual RPS: {actual_rps:.2f}")
    
    def _test_api_latency(self, duration: int, target_rps: int) -> None:
        """Test API endpoint latency"""
        print("\n=== Testing API Latency ===")
        
        api_url = self.stack_outputs.get("ApiUrl")
        if not api_url:
            print("API URL not found")
            return
        
        import urllib.request
        import urllib.error
        
        latencies = []
        errors = 0
        successful = 0
        status_codes = {}
        
        start_time = time.time()
        end_time = start_time + duration
        
        print(f"Testing API for {duration} seconds...")
        
        while time.time() < end_time:
            batch_start = time.time()
            
            # Send batch of requests
            for _ in range(target_rps):
                url = f"{api_url}trending-queries"
                req = urllib.request.Request(url, method="GET")
                
                request_start = time.time()
                try:
                    with urllib.request.urlopen(req, timeout=10) as response:
                        status_code = response.status
                        response.read()  # Consume response
                        
                        latencies.append((time.time() - request_start) * 1000)  # ms
                        successful += 1
                        status_codes[status_code] = status_codes.get(status_code, 0) + 1
                        
                except urllib.error.HTTPError as e:
                    errors += 1
                    status_codes[e.code] = status_codes.get(e.code, 0) + 1
                except Exception as e:
                    errors += 1
            
            # Sleep to maintain target RPS
            elapsed = time.time() - batch_start
            sleep_time = max(0, 1.0 - elapsed)
            time.sleep(sleep_time)
        
        total_time = time.time() - start_time
        actual_rps = (successful + errors) / total_time
        
        self.test_results["api_latency"] = {
            "total_requests": successful + errors,
            "successful": successful,
            "errors": errors,
            "duration_seconds": total_time,
            "actual_rps": actual_rps,
            "target_rps": target_rps,
            "avg_latency_ms": mean(latencies) if latencies else 0,
            "median_latency_ms": median(latencies) if latencies else 0,
            "p95_latency_ms": self._percentile(latencies, 95) if latencies else 0,
            "p99_latency_ms": self._percentile(latencies, 99) if latencies else 0,
            "max_latency_ms": max(latencies) if latencies else 0,
            "status_codes": status_codes
        }
        
        print(f"Completed: {successful} successful, {errors} errors")
        print(f"Actual RPS: {actual_rps:.2f}")
    
    def _percentile(self, data: List[float], percentile: int) -> float:
        """Calculate percentile of data"""
        if not data:
            return 0
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile / 100)
        return sorted_data[min(index, len(sorted_data) - 1)]
    
    def _print_results(self) -> None:
        """Print performance test results"""
        print("\n" + "="*80)
        print("PERFORMANCE TEST RESULTS")
        print("="*80 + "\n")
        
        # Kinesis results
        if "kinesis_throughput" in self.test_results:
            results = self.test_results["kinesis_throughput"]
            print("Kinesis Throughput:")
            print(f"  Total Records:    {results['total_records']}")
            print(f"  Errors:           {results['errors']}")
            print(f"  Duration:         {results['duration_seconds']:.2f}s")
            print(f"  Target RPS:       {results['target_rps']}")
            print(f"  Actual RPS:       {results['actual_rps']:.2f}")
            print(f"  Avg Latency:      {results['avg_latency_ms']:.2f}ms")
            print(f"  Median Latency:   {results['median_latency_ms']:.2f}ms")
            print(f"  P95 Latency:      {results['p95_latency_ms']:.2f}ms")
            print(f"  P99 Latency:      {results['p99_latency_ms']:.2f}ms")
            print(f"  Max Latency:      {results['max_latency_ms']:.2f}ms")
            print()
        
        # API results
        if "api_latency" in self.test_results:
            results = self.test_results["api_latency"]
            print("API Latency:")
            print(f"  Total Requests:   {results['total_requests']}")
            print(f"  Successful:       {results['successful']}")
            print(f"  Errors:           {results['errors']}")
            print(f"  Duration:         {results['duration_seconds']:.2f}s")
            print(f"  Target RPS:       {results['target_rps']}")
            print(f"  Actual RPS:       {results['actual_rps']:.2f}")
            print(f"  Avg Latency:      {results['avg_latency_ms']:.2f}ms")
            print(f"  Median Latency:   {results['median_latency_ms']:.2f}ms")
            print(f"  P95 Latency:      {results['p95_latency_ms']:.2f}ms")
            print(f"  P99 Latency:      {results['p99_latency_ms']:.2f}ms")
            print(f"  Max Latency:      {results['max_latency_ms']:.2f}ms")
            print(f"  Status Codes:     {results['status_codes']}")
            print()
        
        print("="*80 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Run performance tests for OpenSearch Trending Queries"
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
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="Test duration in seconds (default: 60)"
    )
    parser.add_argument(
        "--rps",
        type=int,
        default=10,
        help="Target requests per second (default: 10)"
    )
    
    args = parser.parse_args()
    
    try:
        runner = PerformanceTestRunner(
            environment=args.env,
            region=args.region,
            profile=args.profile
        )
        
        runner.run_all_tests(
            duration_seconds=args.duration,
            requests_per_second=args.rps
        )
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import sys
        sys.exit(1)


if __name__ == "__main__":
    main()
