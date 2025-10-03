#!/usr/bin/env python3
"""
End-to-End Testing Workflow for OpenSearch Trending Queries System

This script exercises the complete pipeline from data ingestion to API retrieval,
validates results, and provides performance benchmarking and cost monitoring.
"""

import argparse
import boto3
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import sys
import requests

# Import from other scripts
sys.path.append('scripts')
from generate_sample_data import SampleDataGenerator, DataIngestionUtility


class E2ETestWorkflow:
    """End-to-end testing workflow orchestrator"""
    
    def __init__(self, env: str, region: str = "us-east-1", profile: str = None):
        """Initialize E2E test workflow"""
        self.env = env
        self.region = region
        self.profile = profile
        
        session_kwargs = {"region_name": region}
        if profile:
            session_kwargs["profile_name"] = profile
        
        session = boto3.Session(**session_kwargs)
        self.sfn = session.client('stepfunctions')
        self.dynamodb = session.client('dynamodb')
        self.cloudwatch = session.client('cloudwatch')
        self.ce = session.client('ce')  # Cost Explorer
        self.apigateway = session.client('apigateway')
        
        # Resource names (auto-detect from environment)
        self.stack_name = f"OpenSearchTrendingQueries-{env}"
        self.stream_name = f"{self.stack_name}-SearchQueryStream"
        self.state_machine_name = f"{self.stack_name}-TrendingQueriesWorkflow"
        self.table_name = f"{self.stack_name}-TrendingQueriesTable"
        
        # Test results
        self.results = {
            "start_time": datetime.utcnow().isoformat(),
            "environment": env,
            "tests": []
        }
    
    def run_complete_pipeline(self, sample_count: int = 1000) -> Dict[str, Any]:
        """Execute complete pipeline test"""
        print(f"\n{'='*60}")
        print("STEP 1: DATA INGESTION")
        print(f"{'='*60}\n")
        
        test_result = {
            "name": "data_ingestion",
            "start_time": time.time()
        }
        
        try:
            # Generate and ingest sample data
            generator = SampleDataGenerator(seed=42)
            logs = generator.generate_batch(sample_count)
            
            ingestion = DataIngestionUtility(
                stream_name=self.stream_name,
                region=self.region,
                profile=self.profile
            )
            
            result = ingestion.ingest_to_kinesis(logs)
            
            test_result["status"] = "PASSED" if result["success"] > 0 else "FAILED"
            test_result["details"] = result
            test_result["duration"] = time.time() - test_result["start_time"]
            
            print(f"\n✓ Data ingestion completed: {result['success']}/{result['total']} records")
            
        except Exception as e:
            test_result["status"] = "FAILED"
            test_result["error"] = str(e)
            test_result["duration"] = time.time() - test_result["start_time"]
            print(f"\n✗ Data ingestion failed: {e}")
        
        self.results["tests"].append(test_result)
        return test_result
    
    def trigger_workflow(self) -> Dict[str, Any]:
        """Trigger Step Functions workflow"""
        print(f"\n{'='*60}")
        print("STEP 2: WORKFLOW EXECUTION")
        print(f"{'='*60}\n")
        
        test_result = {
            "name": "workflow_execution",
            "start_time": time.time()
        }
        
        try:
            # Get state machine ARN
            response = self.sfn.list_state_machines()
            state_machine_arn = None
            
            for sm in response.get('stateMachines', []):
                if self.state_machine_name in sm['name']:
                    state_machine_arn = sm['stateMachineArn']
                    break
            
            if not state_machine_arn:
                raise Exception(f"State machine '{self.state_machine_name}' not found")
            
            # Start execution
            execution_name = f"e2e-test-{int(time.time())}"
            response = self.sfn.start_execution(
                stateMachineArn=state_machine_arn,
                name=execution_name,
                input=json.dumps({"test": True})
            )
            
            execution_arn = response['executionArn']
            print(f"Started execution: {execution_name}")
            print(f"Execution ARN: {execution_arn}")
            
            # Wait for completion (with timeout)
            max_wait = 600  # 10 minutes
            wait_interval = 10
            elapsed = 0
            
            while elapsed < max_wait:
                time.sleep(wait_interval)
                elapsed += wait_interval
                
                status_response = self.sfn.describe_execution(executionArn=execution_arn)
                status = status_response['status']
                
                print(f"Workflow status: {status} (elapsed: {elapsed}s)")
                
                if status in ['SUCCEEDED', 'FAILED', 'TIMED_OUT', 'ABORTED']:
                    break
            
            test_result["status"] = "PASSED" if status == 'SUCCEEDED' else "FAILED"
            test_result["details"] = {
                "execution_arn": execution_arn,
                "final_status": status,
                "elapsed_time": elapsed
            }
            test_result["duration"] = time.time() - test_result["start_time"]
            
            if status == 'SUCCEEDED':
                print(f"\n✓ Workflow completed successfully in {elapsed}s")
            else:
                print(f"\n✗ Workflow ended with status: {status}")
            
        except Exception as e:
            test_result["status"] = "FAILED"
            test_result["error"] = str(e)
            test_result["duration"] = time.time() - test_result["start_time"]
            print(f"\n✗ Workflow execution failed: {e}")
        
        self.results["tests"].append(test_result)
        return test_result
    
    def verify_results(self) -> Dict[str, Any]:
        """Verify trending query results in DynamoDB"""
        print(f"\n{'='*60}")
        print("STEP 3: RESULT VERIFICATION")
        print(f"{'='*60}\n")
        
        test_result = {
            "name": "result_verification",
            "start_time": time.time()
        }
        
        try:
            # Query DynamoDB for today's results
            today = datetime.utcnow().strftime("%Y-%m-%d")
            
            response = self.dynamodb.get_item(
                TableName=self.table_name,
                Key={"date": {"S": today}}
            )
            
            if 'Item' not in response:
                # Try yesterday's date
                yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
                response = self.dynamodb.get_item(
                    TableName=self.table_name,
                    Key={"date": {"S": yesterday}}
                )
            
            if 'Item' in response:
                item = response['Item']
                
                # Parse trending queries
                trending_queries = json.loads(item.get('trending_queries', {}).get('S', '[]'))
                
                # Validate structure
                validations = {
                    "has_data": len(trending_queries) > 0,
                    "has_required_fields": all(
                        'query' in q and 'rank' in q and 'count' in q
                        for q in trending_queries
                    ),
                    "proper_ranking": all(
                        trending_queries[i]['rank'] <= trending_queries[i+1]['rank']
                        for i in range(len(trending_queries)-1)
                    ) if len(trending_queries) > 1 else True
                }
                
                all_valid = all(validations.values())
                
                test_result["status"] = "PASSED" if all_valid else "FAILED"
                test_result["details"] = {
                    "date": item.get('date', {}).get('S'),
                    "query_count": len(trending_queries),
                    "validations": validations,
                    "sample_queries": trending_queries[:3]
                }
                
                print(f"✓ Found trending queries for date: {item.get('date', {}).get('S')}")
                print(f"  Query count: {len(trending_queries)}")
                print(f"  Validations: {validations}")
                print(f"\n  Top 3 queries:")
                for q in trending_queries[:3]:
                    print(f"    {q.get('rank')}. {q.get('query')} (count: {q.get('count')})")
                
            else:
                test_result["status"] = "FAILED"
                test_result["details"] = {"error": "No trending query data found"}
                print("✗ No trending query data found in DynamoDB")
            
            test_result["duration"] = time.time() - test_result["start_time"]
            
        except Exception as e:
            test_result["status"] = "FAILED"
            test_result["error"] = str(e)
            test_result["duration"] = time.time() - test_result["start_time"]
            print(f"\n✗ Result verification failed: {e}")
        
        self.results["tests"].append(test_result)
        return test_result
    
    def test_api_endpoints(self, api_url: str) -> Dict[str, Any]:
        """Test API endpoints"""
        print(f"\n{'='*60}")
        print("STEP 4: API ENDPOINT TESTING")
        print(f"{'='*60}\n")
        
        test_result = {
            "name": "api_testing",
            "start_time": time.time(),
            "endpoints": []
        }
        
        try:
            # Test GET /trending-queries
            endpoint_test = {
                "endpoint": "GET /trending-queries",
                "start_time": time.time()
            }
            
            try:
                response = requests.get(f"{api_url}/trending-queries", timeout=10)
                endpoint_test["status_code"] = response.status_code
                endpoint_test["response_time"] = time.time() - endpoint_test["start_time"]
                
                if response.status_code == 200:
                    data = response.json()
                    endpoint_test["status"] = "PASSED"
                    endpoint_test["data"] = {
                        "query_count": len(data.get('trending_queries', [])),
                        "has_date": 'date' in data
                    }
                    print(f"✓ GET /trending-queries: {response.status_code} ({endpoint_test['response_time']:.3f}s)")
                elif response.status_code == 404:
                    endpoint_test["status"] = "PASSED"
                    endpoint_test["note"] = "No data available (expected for new deployments)"
                    print(f"✓ GET /trending-queries: {response.status_code} (no data yet)")
                else:
                    endpoint_test["status"] = "FAILED"
                    print(f"✗ GET /trending-queries: {response.status_code}")
                
            except Exception as e:
                endpoint_test["status"] = "FAILED"
                endpoint_test["error"] = str(e)
                print(f"✗ GET /trending-queries failed: {e}")
            
            test_result["endpoints"].append(endpoint_test)
            
            # Test GET /trending-queries/{date}
            today = datetime.utcnow().strftime("%Y-%m-%d")
            endpoint_test = {
                "endpoint": f"GET /trending-queries/{today}",
                "start_time": time.time()
            }
            
            try:
                response = requests.get(f"{api_url}/trending-queries/{today}", timeout=10)
                endpoint_test["status_code"] = response.status_code
                endpoint_test["response_time"] = time.time() - endpoint_test["start_time"]
                
                if response.status_code in [200, 404]:
                    endpoint_test["status"] = "PASSED"
                    print(f"✓ GET /trending-queries/{today}: {response.status_code} ({endpoint_test['response_time']:.3f}s)")
                else:
                    endpoint_test["status"] = "FAILED"
                    print(f"✗ GET /trending-queries/{today}: {response.status_code}")
                
            except Exception as e:
                endpoint_test["status"] = "FAILED"
                endpoint_test["error"] = str(e)
                print(f"✗ GET /trending-queries/{today} failed: {e}")
            
            test_result["endpoints"].append(endpoint_test)
            
            # Overall status
            test_result["status"] = "PASSED" if all(
                e.get("status") == "PASSED" for e in test_result["endpoints"]
            ) else "FAILED"
            test_result["duration"] = time.time() - test_result["start_time"]
            
        except Exception as e:
            test_result["status"] = "FAILED"
            test_result["error"] = str(e)
            test_result["duration"] = time.time() - test_result["start_time"]
            print(f"\n✗ API testing failed: {e}")
        
        self.results["tests"].append(test_result)
        return test_result
    
    def performance_benchmark(self, api_url: str, duration: int = 60, rps: int = 10) -> Dict[str, Any]:
        """Run performance benchmark"""
        print(f"\n{'='*60}")
        print("STEP 5: PERFORMANCE BENCHMARKING")
        print(f"{'='*60}\n")
        
        test_result = {
            "name": "performance_benchmark",
            "start_time": time.time(),
            "config": {"duration": duration, "target_rps": rps}
        }
        
        try:
            print(f"Running benchmark: {duration}s duration, {rps} RPS target")
            
            latencies = []
            errors = 0
            success = 0
            
            start_time = time.time()
            request_interval = 1.0 / rps
            
            while time.time() - start_time < duration:
                request_start = time.time()
                
                try:
                    response = requests.get(f"{api_url}/trending-queries", timeout=5)
                    latency = time.time() - request_start
                    latencies.append(latency)
                    
                    if response.status_code in [200, 404]:
                        success += 1
                    else:
                        errors += 1
                except Exception:
                    errors += 1
                
                # Rate limiting
                elapsed = time.time() - request_start
                if elapsed < request_interval:
                    time.sleep(request_interval - elapsed)
            
            # Calculate metrics
            if latencies:
                latencies.sort()
                metrics = {
                    "total_requests": len(latencies) + errors,
                    "successful_requests": success,
                    "failed_requests": errors,
                    "avg_latency": sum(latencies) / len(latencies),
                    "median_latency": latencies[len(latencies) // 2],
                    "p95_latency": latencies[int(len(latencies) * 0.95)],
                    "p99_latency": latencies[int(len(latencies) * 0.99)],
                    "max_latency": max(latencies),
                    "min_latency": min(latencies),
                    "actual_rps": len(latencies) / duration
                }
                
                test_result["status"] = "PASSED"
                test_result["metrics"] = metrics
                
                print(f"\nPerformance Metrics:")
                print(f"  Total Requests: {metrics['total_requests']}")
                print(f"  Success Rate: {success}/{metrics['total_requests']} ({100*success/metrics['total_requests']:.1f}%)")
                print(f"  Actual RPS: {metrics['actual_rps']:.2f}")
                print(f"  Avg Latency: {metrics['avg_latency']*1000:.2f}ms")
                print(f"  P95 Latency: {metrics['p95_latency']*1000:.2f}ms")
                print(f"  P99 Latency: {metrics['p99_latency']*1000:.2f}ms")
                print(f"  Max Latency: {metrics['max_latency']*1000:.2f}ms")
                
            else:
                test_result["status"] = "FAILED"
                test_result["error"] = "No successful requests"
            
            test_result["duration"] = time.time() - test_result["start_time"]
            
        except Exception as e:
            test_result["status"] = "FAILED"
            test_result["error"] = str(e)
            test_result["duration"] = time.time() - test_result["start_time"]
            print(f"\n✗ Performance benchmark failed: {e}")
        
        self.results["tests"].append(test_result)
        return test_result
    
    def cost_monitoring(self) -> Dict[str, Any]:
        """Monitor and report costs"""
        print(f"\n{'='*60}")
        print("STEP 6: COST MONITORING")
        print(f"{'='*60}\n")
        
        test_result = {
            "name": "cost_monitoring",
            "start_time": time.time()
        }
        
        try:
            # Get cost for last 7 days
            end_date = datetime.utcnow().date()
            start_date = end_date - timedelta(days=7)
            
            response = self.ce.get_cost_and_usage(
                TimePeriod={
                    'Start': start_date.strftime('%Y-%m-%d'),
                    'End': end_date.strftime('%Y-%m-%d')
                },
                Granularity='DAILY',
                Metrics=['UnblendedCost'],
                GroupBy=[
                    {'Type': 'DIMENSION', 'Key': 'SERVICE'}
                ],
                Filter={
                    'Tags': {
                        'Key': 'Environment',
                        'Values': [self.env]
                    }
                }
            )
            
            # Aggregate costs by service
            service_costs = {}
            total_cost = 0
            
            for result in response.get('ResultsByTime', []):
                for group in result.get('Groups', []):
                    service = group['Keys'][0]
                    cost = float(group['Metrics']['UnblendedCost']['Amount'])
                    service_costs[service] = service_costs.get(service, 0) + cost
                    total_cost += cost
            
            test_result["status"] = "PASSED"
            test_result["details"] = {
                "period": f"{start_date} to {end_date}",
                "total_cost": round(total_cost, 2),
                "service_costs": {k: round(v, 2) for k, v in service_costs.items()}
            }
            
            print(f"Cost Report ({start_date} to {end_date}):")
            print(f"  Total Cost: ${total_cost:.2f}")
            print(f"\n  By Service:")
            for service, cost in sorted(service_costs.items(), key=lambda x: x[1], reverse=True):
                print(f"    {service}: ${cost:.2f}")
            
            test_result["duration"] = time.time() - test_result["start_time"]
            
        except Exception as e:
            test_result["status"] = "FAILED"
            test_result["error"] = str(e)
            test_result["duration"] = time.time() - test_result["start_time"]
            print(f"\n✗ Cost monitoring failed: {e}")
            print("  Note: Cost Explorer API may not be enabled or may require permissions")
        
        self.results["tests"].append(test_result)
        return test_result
    
    def generate_report(self, output_file: str = None) -> Dict[str, Any]:
        """Generate test report"""
        self.results["end_time"] = datetime.utcnow().isoformat()
        self.results["total_duration"] = sum(t.get("duration", 0) for t in self.results["tests"])
        self.results["passed"] = sum(1 for t in self.results["tests"] if t.get("status") == "PASSED")
        self.results["failed"] = sum(1 for t in self.results["tests"] if t.get("status") == "FAILED")
        self.results["overall_status"] = "PASSED" if self.results["failed"] == 0 else "FAILED"
        
        print(f"\n{'='*60}")
        print("TEST SUMMARY")
        print(f"{'='*60}\n")
        print(f"Environment: {self.results['environment']}")
        print(f"Total Duration: {self.results['total_duration']:.2f}s")
        print(f"Tests Passed: {self.results['passed']}/{len(self.results['tests'])}")
        print(f"Tests Failed: {self.results['failed']}/{len(self.results['tests'])}")
        print(f"Overall Status: {self.results['overall_status']}")
        
        if output_file:
            with open(output_file, 'w') as f:
                json.dump(self.results, f, indent=2)
            print(f"\nDetailed report saved to: {output_file}")
        
        return self.results


def main():
    parser = argparse.ArgumentParser(
        description="End-to-end testing workflow for OpenSearch Trending Queries system"
    )
    
    parser.add_argument(
        "--env",
        required=True,
        choices=["dev", "staging", "prod"],
        help="Environment to test"
    )
    parser.add_argument(
        "--api-url",
        help="API Gateway URL (required for API tests)"
    )
    parser.add_argument(
        "--sample-count",
        type=int,
        default=1000,
        help="Number of sample records to generate (default: 1000)"
    )
    parser.add_argument(
        "--skip-ingestion",
        action="store_true",
        help="Skip data ingestion step"
    )
    parser.add_argument(
        "--skip-workflow",
        action="store_true",
        help="Skip workflow execution step"
    )
    parser.add_argument(
        "--skip-api",
        action="store_true",
        help="Skip API testing step"
    )
    parser.add_argument(
        "--skip-benchmark",
        action="store_true",
        help="Skip performance benchmark"
    )
    parser.add_argument(
        "--skip-cost",
        action="store_true",
        help="Skip cost monitoring"
    )
    parser.add_argument(
        "--benchmark-duration",
        type=int,
        default=60,
        help="Benchmark duration in seconds (default: 60)"
    )
    parser.add_argument(
        "--benchmark-rps",
        type=int,
        default=10,
        help="Benchmark target RPS (default: 10)"
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
        "--output",
        help="Output file for test report (JSON)"
    )
    
    args = parser.parse_args()
    
    # Initialize workflow
    workflow = E2ETestWorkflow(
        env=args.env,
        region=args.region,
        profile=args.profile
    )
    
    print(f"\n{'#'*60}")
    print(f"# END-TO-END TEST WORKFLOW")
    print(f"# Environment: {args.env}")
    print(f"# Region: {args.region}")
    print(f"{'#'*60}")
    
    # Execute test steps
    if not args.skip_ingestion:
        workflow.run_complete_pipeline(sample_count=args.sample_count)
    
    if not args.skip_workflow:
        workflow.trigger_workflow()
    
    # Verify results
    workflow.verify_results()
    
    # API tests
    if not args.skip_api and args.api_url:
        workflow.test_api_endpoints(args.api_url)
        
        if not args.skip_benchmark:
            workflow.performance_benchmark(
                api_url=args.api_url,
                duration=args.benchmark_duration,
                rps=args.benchmark_rps
            )
    elif not args.skip_api:
        print("\n⚠ Skipping API tests: --api-url not provided")
    
    # Cost monitoring
    if not args.skip_cost:
        workflow.cost_monitoring()
    
    # Generate report
    report = workflow.generate_report(output_file=args.output)
    
    # Exit with appropriate code
    sys.exit(0 if report["overall_status"] == "PASSED" else 1)


if __name__ == "__main__":
    main()
