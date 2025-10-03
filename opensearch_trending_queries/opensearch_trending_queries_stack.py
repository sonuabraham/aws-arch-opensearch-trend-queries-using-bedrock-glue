"""
Main CDK Stack for OpenSearch Trending Queries Architecture
"""
from aws_cdk import (
    Stack,
    Tags,
    CfnOutput,
)
from constructs import Construct
from typing import Dict, Any

from .constructs.data_ingestion import DataIngestionConstruct
from .constructs.data_processing import DataProcessingConstruct
from .constructs.analytics import AnalyticsConstruct
from .constructs.orchestration import OrchestrationConstruct
from .constructs.storage import StorageConstruct
from .constructs.api import ApiConstruct
from .constructs.security import SecurityConstruct
from .constructs.monitoring import MonitoringConstruct
from .config.environment_config import EnvironmentConfig


class OpenSearchTrendingQueriesStack(Stack):
    """
    Main stack that orchestrates all components of the OpenSearch Trending Queries system
    """

    def __init__(self, scope: Construct, construct_id: str, env_name: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Load environment configuration
        self.config = EnvironmentConfig(env_name)
        
        # Apply common tags
        self._apply_tags()
        
        # Create core infrastructure components
        self._create_infrastructure()

    def _apply_tags(self) -> None:
        """Apply common tags to all resources in the stack"""
        Tags.of(self).add("Project", "OpenSearchTrendingQueries")
        Tags.of(self).add("Environment", self.config.env_name)
        Tags.of(self).add("ManagedBy", "CDK")

    def _create_infrastructure(self) -> None:
        """Create all infrastructure components"""
        
        # 0. Security layer (IAM roles, KMS keys, VPC endpoints) - Created first
        self.security = SecurityConstruct(
            self, "Security",
            config=self.config
        )
        
        # 1. Storage layer (S3, DynamoDB)
        self.storage = StorageConstruct(
            self, "Storage",
            config=self.config,
            s3_kms_key=self.security.s3_kms_key,
            dynamodb_kms_key=self.security.dynamodb_kms_key,
            logs_kms_key=self.security.logs_kms_key,
            compression_lambda_role=self.security.compression_lambda_role
        )
        
        # Update security construct with storage resources for resource policies
        self.security.raw_data_bucket = self.storage.raw_data_bucket
        self.security.processed_data_bucket = self.storage.processed_data_bucket
        self.security.query_results_bucket = self.storage.query_results_bucket
        self.security.trending_queries_table = self.storage.trending_queries_table
        self.security._configure_resource_policies()
        
        # 2. Data ingestion (Kinesis, S3 integration)
        self.data_ingestion = DataIngestionConstruct(
            self, "DataIngestion",
            config=self.config,
            raw_data_bucket=self.storage.raw_data_bucket,
            kinesis_kms_key=self.security.kinesis_kms_key,
            logs_kms_key=self.security.logs_kms_key,
            kinesis_producer_role=self.security.kinesis_producer_role,
            firehose_delivery_role=self.security.firehose_delivery_role
        )
        
        # 3. Data processing (Glue, Athena)
        self.data_processing = DataProcessingConstruct(
            self, "DataProcessing",
            config=self.config,
            raw_data_bucket=self.storage.raw_data_bucket,
            processed_data_bucket=self.storage.processed_data_bucket,
            query_results_bucket=self.storage.query_results_bucket,
            glue_crawler_role=self.security.glue_crawler_role,
            glue_job_role=self.security.glue_job_role,
            logs_kms_key=self.security.logs_kms_key
        )
        
        # 4. Analytics (ML, Bedrock)
        self.analytics = AnalyticsConstruct(
            self, "Analytics",
            config=self.config,
            processed_data_bucket=self.storage.processed_data_bucket,
            results_table=self.storage.trending_queries_table,
            glue_database_name=self.data_processing.glue_database.ref,
            glue_job_role=self.data_processing.glue_job_role,
            bedrock_lambda_role=self.security.bedrock_lambda_role
        )
        
        # 5. Orchestration (Step Functions, EventBridge)
        self.orchestration = OrchestrationConstruct(
            self, "Orchestration",
            config=self.config,
            glue_crawler=self.data_processing.glue_crawler,
            glue_job=self.data_processing.consolidation_job,
            clustering_job=self.analytics.clustering_job,
            classification_function=self.analytics.classification_function,
            step_functions_role=self.security.step_functions_role,
            logs_kms_key=self.security.logs_kms_key
        )
        
        # 6. API layer (API Gateway, Lambda)
        self.api = ApiConstruct(
            self, "Api",
            config=self.config,
            trending_queries_table=self.storage.trending_queries_table,
            api_lambda_role=self.security.api_lambda_role,
            logs_kms_key=self.security.logs_kms_key
        )
        
        # 7. Monitoring (CloudWatch, X-Ray)
        self.monitoring = MonitoringConstruct(
            self, "Monitoring",
            config=self.config,
            kinesis_stream=self.data_ingestion.kinesis_stream,
            step_function=self.orchestration.step_function,
            api_gateway=self.api.api_gateway,
            lambda_functions={
                "get_trending_queries": self.api.get_trending_queries_function,
                "get_trending_queries_by_date": self.api.get_trending_queries_by_date_function,
                "bedrock_classification": self.analytics.classification_function,
                "log_compression": self.storage.compression_function
            },
            trending_queries_table=self.storage.trending_queries_table,
            glue_jobs={
                "consolidation": self.data_processing.consolidation_job,
                "clustering": self.analytics.clustering_job
            }
        )
        
        # Export stack outputs for validation and integration
        self._create_outputs()
    
def _create_outputs(self) -> None:
        """Create CloudFormation outputs for validation and integration"""
        
        # Storage outputs
        CfnOutput(
            self, "RawDataBucketName",
            value=self.storage.raw_data_bucket.bucket_name,
            description="S3 bucket for raw search query logs"
        )
        
        CfnOutput(
            self, "ProcessedDataBucketName",
            value=self.storage.processed_data_bucket.bucket_name,
            description="S3 bucket for processed data"
        )
        
        CfnOutput(
            self, "QueryResultsBucketName",
            value=self.storage.query_results_bucket.bucket_name,
            description="S3 bucket for Athena query results"
        )
        
        CfnOutput(
            self, "TrendingQueriesTableName",
            value=self.storage.trending_queries_table.table_name,
            description="DynamoDB table for trending queries"
        )
        
        # Data ingestion outputs
        CfnOutput(
            self, "KinesisStreamName",
            value=self.data_ingestion.kinesis_stream.stream_name,
            description="Kinesis stream for log ingestion"
        )
        
        CfnOutput(
            self, "KinesisStreamArn",
            value=self.data_ingestion.kinesis_stream.stream_arn,
            description="Kinesis stream ARN"
        )
        
        # Data processing outputs
        CfnOutput(
            self, "GlueDatabaseName",
            value=self.data_processing.glue_database.ref,
            description="Glue database name"
        )
        
        CfnOutput(
            self, "GlueCrawlerName",
            value=self.data_processing.glue_crawler.name,
            description="Glue crawler name"
        )
        
        CfnOutput(
            self, "AthenaWorkgroupName",
            value=self.data_processing.athena_workgroup.name,
            description="Athena workgroup name"
        )
        
        # Orchestration outputs
        CfnOutput(
            self, "StepFunctionArn",
            value=self.orchestration.step_function.state_machine_arn,
            description="Step Functions state machine ARN"
        )
        
        CfnOutput(
            self, "StepFunctionName",
            value=self.orchestration.step_function.state_machine_name,
            description="Step Functions state machine name"
        )
        
        # API outputs
        CfnOutput(
            self, "ApiUrl",
            value=self.api.api_gateway.url,
            description="API Gateway endpoint URL"
        )
        
        CfnOutput(
            self, "ApiId",
            value=self.api.api_gateway.rest_api_id,
            description="API Gateway REST API ID"
        )
        
        # Lambda function outputs
        CfnOutput(
            self, "GetTrendingQueriesFunctionName",
            value=self.api.get_trending_queries_function.function_name,
            description="Lambda function for GET /trending-queries"
        )
        
        CfnOutput(
            self, "GetTrendingQueriesByDateFunctionName",
            value=self.api.get_trending_queries_by_date_function.function_name,
            description="Lambda function for GET /trending-queries/{date}"
        )
        
        CfnOutput(
            self, "BedrockClassificationFunctionName",
            value=self.analytics.classification_function.function_name,
            description="Lambda function for Bedrock classification"
        )
        
        CfnOutput(
            self, "LogCompressionFunctionName",
            value=self.storage.compression_function.function_name,
            description="Lambda function for log compression"
        )
        
        # Monitoring outputs
        CfnOutput(
            self, "DashboardName",
            value=self.monitoring.dashboard.dashboard_name,
            description="CloudWatch dashboard name"
        )
