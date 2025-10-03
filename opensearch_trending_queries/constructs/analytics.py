"""
Analytics Construct - Machine Learning and Bedrock integration
"""
from aws_cdk import (
    aws_s3 as s3,
    aws_dynamodb as dynamodb,
    aws_glue as glue,
    aws_iam as iam,
    aws_lambda as lambda_,
    Duration,
)
from constructs import Construct
from ..config.environment_config import EnvironmentConfig


class AnalyticsConstruct(Construct):
    """Construct for analytics and ML components"""
    
    def __init__(
        self, 
        scope: Construct, 
        construct_id: str, 
        config: EnvironmentConfig,
        processed_data_bucket: s3.Bucket, 
        results_table: dynamodb.Table,
        glue_database_name: str, 
        glue_job_role: iam.Role,
        bedrock_lambda_role: iam.Role = None
    ):
        super().__init__(scope, construct_id)
        
        self.config = config
        self.processed_data_bucket = processed_data_bucket
        self.results_table = results_table
        self.glue_database_name = glue_database_name
        self.glue_job_role = glue_job_role
        self.bedrock_lambda_role = bedrock_lambda_role
        
        # Create K-means clustering job
        self._create_kmeans_clustering_job()
        
        # Create Bedrock classification Lambda function
        self._create_bedrock_classification_function()
    
    def _create_kmeans_clustering_job(self) -> None:
        """Create AWS Glue job for K-means clustering"""
        
        # Get configuration
        max_concurrent_runs = self.config.get("glue", "max_concurrent_runs")
        timeout_minutes = self.config.get("glue", "timeout_minutes")
        cluster_count = self.config.get("ml", "cluster_count", 10)
        max_iterations = self.config.get("ml", "max_iterations", 20)
        
        # Create the K-means clustering Glue job
        self.clustering_job = glue.CfnJob(
            self, "KMeansClusteringJob",
            name=f"{self.config.resource_prefix}-kmeans-clustering",
            role=self.glue_job_role.role_arn,
            description="K-means clustering job for search query analysis with vector embeddings",
            command=glue.CfnJob.JobCommandProperty(
                name="glueetl",
                script_location=f"s3://{self.processed_data_bucket.bucket_name}/scripts/kmeans_clustering_job.py",
                python_version="3"
            ),
            default_arguments={
                "--job-language": "python",
                "--job-bookmark-option": "job-bookmark-disable",
                "--enable-metrics": "true",
                "--enable-continuous-cloudwatch-log": "true",
                "--enable-spark-ui": "true",
                "--spark-event-logs-path": f"s3://{self.processed_data_bucket.bucket_name}/spark-logs/",
                "--TempDir": f"s3://{self.processed_data_bucket.bucket_name}/temp/",
                "--database_name": self.glue_database_name,
                "--processed_data_bucket": self.processed_data_bucket.bucket_name,
                "--cluster_count": str(cluster_count),
                "--max_iterations": str(max_iterations),
                "--enable-glue-datacatalog": "true"
            },
            execution_property=glue.CfnJob.ExecutionPropertyProperty(
                max_concurrent_runs=max_concurrent_runs
            ),
            timeout=timeout_minutes,
            glue_version="4.0",
            max_retries=2,
            worker_type="G.1X",
            number_of_workers=3
        )
    
    def _create_bedrock_classification_function(self) -> None:
        """Create Lambda function for Bedrock LLM classification"""
        
        # Use provided role or create fallback role
        if self.bedrock_lambda_role:
            bedrock_lambda_role = self.bedrock_lambda_role
        else:
            # Create IAM role for Lambda function
            bedrock_lambda_role = iam.Role(
                self, "BedrockClassificationRole",
                role_name=f"{self.config.resource_prefix}-bedrock-classification",
                assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
                description="Role for Lambda function to classify queries using Amazon Bedrock",
                managed_policies=[
                    iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
                ]
            )
            
            # Grant Bedrock permissions
            bedrock_lambda_role.add_to_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "bedrock:InvokeModel",
                        "bedrock:InvokeModelWithResponseStream"
                    ],
                    resources=[
                        f"arn:aws:bedrock:{self.region}::foundation-model/*"
                    ]
                )
            )
            
            # Grant S3 permissions to read clustered data
            self.processed_data_bucket.grant_read(bedrock_lambda_role)
            
            # Grant DynamoDB permissions to write results
            self.results_table.grant_write_data(bedrock_lambda_role)
        
        # Create Lambda function
        self.classification_function = lambda_.Function(
            self, "BedrockClassificationFunction",
            function_name=f"{self.config.resource_prefix}-bedrock-classification",
            description="Classifies trending queries using Amazon Bedrock LLM",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="bedrock_classification.handler",
            code=lambda_.Code.from_asset("opensearch_trending_queries/lambda"),
            role=bedrock_lambda_role,
            timeout=Duration.minutes(5),
            memory_size=512,
            environment={
                "PROCESSED_DATA_BUCKET": self.processed_data_bucket.bucket_name,
                "RESULTS_TABLE_NAME": self.results_table.table_name,
                "BEDROCK_MODEL_ID": self.config.get("bedrock", "model_id", "anthropic.claude-3-sonnet-20240229-v1:0"),
                "MAX_RETRIES": str(self.config.get("bedrock", "max_retries", 3)),
                "RETRY_DELAY": str(self.config.get("bedrock", "retry_delay", 2))
            },
            tracing=lambda_.Tracing.ACTIVE  # Enable X-Ray tracing
        )