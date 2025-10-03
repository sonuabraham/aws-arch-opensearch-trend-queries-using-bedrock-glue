"""
Data Processing Construct - AWS Glue and Athena resources
"""
from aws_cdk import (
    Duration,
    aws_glue as glue,
    aws_athena as athena,
    aws_s3 as s3,
    aws_iam as iam,
    aws_logs as logs,
    RemovalPolicy,
)
from constructs import Construct
from ..config.environment_config import EnvironmentConfig


class DataProcessingConstruct(Construct):
    """Construct for data processing components using AWS Glue and Athena"""
    
    def __init__(
        self, 
        scope: Construct, 
        construct_id: str, 
        config: EnvironmentConfig, 
        raw_data_bucket: s3.Bucket, 
        processed_data_bucket: s3.Bucket, 
        query_results_bucket: s3.Bucket,
        glue_crawler_role: iam.Role = None,
        glue_job_role: iam.Role = None,
        logs_kms_key = None
    ):
        super().__init__(scope, construct_id)
        
        self.config = config
        self.raw_data_bucket = raw_data_bucket
        self.processed_data_bucket = processed_data_bucket
        self._query_results_bucket = query_results_bucket
        self._provided_glue_crawler_role = glue_crawler_role
        self._provided_glue_job_role = glue_job_role
        self.logs_kms_key = logs_kms_key
        
        # Create Glue Database and resources
        self._create_glue_database()
        self._create_glue_iam_roles()
        self._create_glue_crawler()
        self._create_glue_etl_jobs()
        
        # Create Athena workspace configuration
        self._create_athena_workgroup()
    
    def _create_glue_database(self) -> None:
        """Create Glue Database for data catalog"""
        
        self.glue_database = glue.CfnDatabase(
            self, "SearchQueriesDatabase",
            catalog_id=self.account,
            database_input=glue.CfnDatabase.DatabaseInputProperty(
                name=f"{self.config.resource_prefix.replace('-', '_')}_db",
                description="Database for search queries trending analysis",
                parameters={
                    "classification": "parquet",
                    "compressionType": "gzip"
                }
            )
        )
    
    def _create_glue_iam_roles(self) -> None:
        """Create IAM roles for Glue service access (fallback if not provided by SecurityConstruct)"""
        
        # Use provided roles or create fallback roles
        if self._provided_glue_crawler_role:
            self.glue_crawler_role = self._provided_glue_crawler_role
        else:
            # Role for Glue Crawler
            self.glue_crawler_role = iam.Role(
                self, "GlueCrawlerRole",
                role_name=f"{self.config.resource_prefix}-glue-crawler",
                assumed_by=iam.ServicePrincipal("glue.amazonaws.com"),
                description="Role for Glue crawler to access S3 and create table definitions",
                managed_policies=[
                    iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSGlueServiceRole")
                ]
            )
            
            # Grant S3 permissions to crawler
            self.raw_data_bucket.grant_read(self.glue_crawler_role)
            self.processed_data_bucket.grant_read_write(self.glue_crawler_role)
        
        if self._provided_glue_job_role:
            self.glue_job_role = self._provided_glue_job_role
        else:
            # Role for Glue ETL Jobs
            self.glue_job_role = iam.Role(
                self, "GlueJobRole",
                role_name=f"{self.config.resource_prefix}-glue-job",
                assumed_by=iam.ServicePrincipal("glue.amazonaws.com"),
                description="Role for Glue ETL jobs to process and consolidate data",
                managed_policies=[
                    iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSGlueServiceRole")
                ]
            )
            
            # Grant S3 permissions to ETL jobs
            self.raw_data_bucket.grant_read(self.glue_job_role)
            self.processed_data_bucket.grant_read_write(self.glue_job_role)
            
            # Grant CloudWatch Logs permissions
            self.glue_job_role.add_to_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "logs:CreateLogGroup",
                        "logs:CreateLogStream",
                        "logs:PutLogEvents"
                    ],
                    resources=[f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws-glue/*"]
                )
            )
    
    def _create_glue_crawler(self) -> None:
        """Create Glue crawler to automatically discover and catalog data schema"""
        
        # Create CloudWatch log group for crawler with encryption
        log_group_kwargs = {
            "log_group_name": f"/aws-glue/crawlers/{self.config.resource_prefix}-search-queries",
            "retention": logs.RetentionDays.ONE_WEEK,
            "removal_policy": RemovalPolicy.DESTROY
        }
        
        # Add KMS encryption if available
        if self.logs_kms_key:
            log_group_kwargs["encryption_key"] = self.logs_kms_key
        
        crawler_log_group = logs.LogGroup(self, "CrawlerLogGroup", **log_group_kwargs)
        
        # Create the Glue crawler
        self.glue_crawler = glue.CfnCrawler(
            self, "SearchQueriesCrawler",
            name=f"{self.config.resource_prefix}-search-queries-crawler",
            role=self.glue_crawler_role.role_arn,
            database_name=self.glue_database.ref,
            description="Crawler to discover and catalog search query data schema",
            targets=glue.CfnCrawler.TargetsProperty(
                s3_targets=[
                    glue.CfnCrawler.S3TargetProperty(
                        path=f"s3://{self.raw_data_bucket.bucket_name}/search-queries/",
                        exclusions=["errors/**"]
                    )
                ]
            ),
            configuration="""{
                "Version": 1.0,
                "CrawlerOutput": {
                    "Partitions": {
                        "AddOrUpdateBehavior": "InheritFromTable"
                    },
                    "Tables": {
                        "AddOrUpdateBehavior": "MergeNewColumns"
                    }
                },
                "Grouping": {
                    "TableGroupingPolicy": "CombineCompatibleSchemas"
                }
            }""",
            schema_change_policy=glue.CfnCrawler.SchemaChangePolicyProperty(
                update_behavior="UPDATE_IN_DATABASE",
                delete_behavior="LOG"
            ),
            recrawl_policy=glue.CfnCrawler.RecrawlPolicyProperty(
                recrawl_behavior="CRAWL_EVERYTHING"
            )
        )
    
    def _create_glue_etl_jobs(self) -> None:
        """Create Glue ETL job definitions for data consolidation"""
        
        # Get Glue job configuration
        max_concurrent_runs = self.config.get("glue", "max_concurrent_runs")
        timeout_minutes = self.config.get("glue", "timeout_minutes")
        
        # Create the consolidation job script in S3
        self._create_consolidation_job_script()
        
        # Create the Glue ETL job for data consolidation
        self.consolidation_job = glue.CfnJob(
            self, "DataConsolidationJob",
            name=f"{self.config.resource_prefix}-data-consolidation",
            role=self.glue_job_role.role_arn,
            description="ETL job to consolidate and transform search query data",
            command=glue.CfnJob.JobCommandProperty(
                name="glueetl",
                script_location=f"s3://{self.processed_data_bucket.bucket_name}/scripts/consolidation_job.py",
                python_version="3"
            ),
            default_arguments={
                "--job-language": "python",
                "--job-bookmark-option": "job-bookmark-enable",
                "--enable-metrics": "true",
                "--enable-continuous-cloudwatch-log": "true",
                "--enable-spark-ui": "true",
                "--spark-event-logs-path": f"s3://{self.processed_data_bucket.bucket_name}/spark-logs/",
                "--TempDir": f"s3://{self.processed_data_bucket.bucket_name}/temp/",
                "--database_name": self.glue_database.ref,
                "--raw_data_bucket": self.raw_data_bucket.bucket_name,
                "--processed_data_bucket": self.processed_data_bucket.bucket_name
            },
            execution_property=glue.CfnJob.ExecutionPropertyProperty(
                max_concurrent_runs=max_concurrent_runs
            ),
            timeout=timeout_minutes,
            glue_version="4.0",
            max_retries=2,
            worker_type="G.1X",
            number_of_workers=2
        )
        
        # Create clustering preparation job
        self._create_clustering_job_script()
        
        self.clustering_prep_job = glue.CfnJob(
            self, "ClusteringPrepJob",
            name=f"{self.config.resource_prefix}-clustering-prep",
            role=self.glue_job_role.role_arn,
            description="ETL job to prepare data for K-means clustering analysis",
            command=glue.CfnJob.JobCommandProperty(
                name="glueetl",
                script_location=f"s3://{self.processed_data_bucket.bucket_name}/scripts/clustering_prep_job.py",
                python_version="3"
            ),
            default_arguments={
                "--job-language": "python",
                "--job-bookmark-option": "job-bookmark-enable",
                "--enable-metrics": "true",
                "--enable-continuous-cloudwatch-log": "true",
                "--enable-spark-ui": "true",
                "--spark-event-logs-path": f"s3://{self.processed_data_bucket.bucket_name}/spark-logs/",
                "--TempDir": f"s3://{self.processed_data_bucket.bucket_name}/temp/",
                "--database_name": self.glue_database.ref,
                "--processed_data_bucket": self.processed_data_bucket.bucket_name
            },
            execution_property=glue.CfnJob.ExecutionPropertyProperty(
                max_concurrent_runs=max_concurrent_runs
            ),
            timeout=timeout_minutes,
            glue_version="4.0",
            max_retries=2,
            worker_type="G.1X",
            number_of_workers=2
        )
    
    def _create_consolidation_job_script(self) -> None:
        """Create the Python script for the data consolidation Glue job"""
        
        consolidation_script = '''import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql import functions as F
from pyspark.sql.types import *
from datetime import datetime, timedelta

# Get job parameters
args = getResolvedOptions(sys.argv, [
    'JOB_NAME',
    'database_name',
    'raw_data_bucket',
    'processed_data_bucket'
])

# Initialize Glue context
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

try:
    # Read search query data from Glue catalog
    search_queries_df = glueContext.create_dynamic_frame.from_catalog(
        database=args['database_name'],
        table_name="search_queries"
    ).toDF()
    
    # Data consolidation and aggregation
    consolidated_df = search_queries_df.groupBy(
        "query_text",
        F.to_date("timestamp").alias("date")
    ).agg(
        F.count("*").alias("query_count"),
        F.countDistinct("user_id").alias("unique_users"),
        F.avg("results_count").alias("avg_results_count"),
        F.avg(F.when(F.col("click_through") == True, 1).otherwise(0)).alias("click_through_rate"),
        F.first("source").alias("source")
    )
    
    # Add partitioning columns
    consolidated_df = consolidated_df.withColumn("year", F.year("date")) \\
                                   .withColumn("month", F.month("date")) \\
                                   .withColumn("day", F.dayofmonth("date"))
    
    # Write consolidated data to S3 in Parquet format
    consolidated_df.write \\
        .mode("overwrite") \\
        .partitionBy("year", "month", "day") \\
        .parquet(f"s3://{args['processed_data_bucket']}/consolidated-queries/")
    
    print("Data consolidation completed successfully")
    
except Exception as e:
    print(f"Error in data consolidation: {str(e)}")
    raise e
finally:
    job.commit()
'''
        
        # Upload script to S3 (this would typically be done during deployment)
        # For now, we'll create a placeholder that indicates the script location
        self.consolidation_script_location = f"s3://{self.processed_data_bucket.bucket_name}/scripts/consolidation_job.py"
    
    def _create_clustering_job_script(self) -> None:
        """Create the Python script for the clustering preparation Glue job"""
        
        clustering_script = '''import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql import functions as F
from pyspark.ml.feature import Tokenizer, HashingTF, IDF
from pyspark.ml.clustering import KMeans
from pyspark.ml import Pipeline
from datetime import datetime, timedelta

# Get job parameters
args = getResolvedOptions(sys.argv, [
    'JOB_NAME',
    'database_name',
    'processed_data_bucket'
])

# Initialize Glue context
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

try:
    # Read consolidated data
    consolidated_df = spark.read.parquet(
        f"s3://{args['processed_data_bucket']}/consolidated-queries/"
    )
    
    # Filter for recent data (last 7 days)
    recent_date = datetime.now() - timedelta(days=7)
    recent_df = consolidated_df.filter(F.col("date") >= recent_date)
    
    # Prepare data for clustering - create TF-IDF vectors
    tokenizer = Tokenizer(inputCol="query_text", outputCol="words")
    hashingTF = HashingTF(inputCol="words", outputCol="rawFeatures", numFeatures=1000)
    idf = IDF(inputCol="rawFeatures", outputCol="features")
    
    # Create pipeline for feature extraction
    pipeline = Pipeline(stages=[tokenizer, hashingTF, idf])
    model = pipeline.fit(recent_df)
    feature_df = model.transform(recent_df)
    
    # Apply K-means clustering
    kmeans = KMeans(k=10, seed=42, featuresCol="features", predictionCol="cluster_id")
    kmeans_model = kmeans.fit(feature_df)
    clustered_df = kmeans_model.transform(feature_df)
    
    # Select relevant columns and write results
    result_df = clustered_df.select(
        "query_text",
        "date",
        "query_count",
        "unique_users",
        "avg_results_count",
        "click_through_rate",
        "cluster_id"
    )
    
    # Write clustering results to S3
    result_df.write \\
        .mode("overwrite") \\
        .partitionBy("date") \\
        .parquet(f"s3://{args['processed_data_bucket']}/clustered-queries/")
    
    print("Clustering preparation completed successfully")
    
except Exception as e:
    print(f"Error in clustering preparation: {str(e)}")
    raise e
finally:
    job.commit()
'''
        
        # Upload script to S3 (this would typically be done during deployment)
        self.clustering_script_location = f"s3://{self.processed_data_bucket.bucket_name}/scripts/clustering_prep_job.py"
    
    def _create_athena_workgroup(self) -> None:
        """Create Athena workgroup with query result location"""
        
        # Use the query results bucket passed from storage construct
        query_results_bucket = self._query_results_bucket
        
        # Create Athena workgroup
        self.athena_workgroup = athena.CfnWorkGroup(
            self, "SearchQueriesWorkGroup",
            name=f"{self.config.resource_prefix}-workgroup",
            description="Athena workgroup for search queries analysis",
            state="ENABLED",
            work_group_configuration=athena.CfnWorkGroup.WorkGroupConfigurationProperty(
                result_configuration=athena.CfnWorkGroup.ResultConfigurationProperty(
                    output_location=f"s3://{query_results_bucket.bucket_name}/athena-results/",
                    encryption_configuration=athena.CfnWorkGroup.EncryptionConfigurationProperty(
                        encryption_option="SSE_S3"
                    )
                ),
                enforce_work_group_configuration=True,
                publish_cloud_watch_metrics=True,
                bytes_scanned_cutoff_per_query=1000000000,  # 1GB limit
                requester_pays_enabled=False
            ),
            tags=[
                athena.CfnWorkGroup.TagProperty(key="Project", value="OpenSearchTrendingQueries"),
                athena.CfnWorkGroup.TagProperty(key="Environment", value=self.config.env_name)
            ]
        )
        
        # Create IAM role for Athena queries
        self.athena_query_role = iam.Role(
            self, "AthenaQueryRole",
            role_name=f"{self.config.resource_prefix}-athena-query",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Role for Lambda functions to execute Athena queries"
        )
        
        # Grant permissions for Athena queries
        self.athena_query_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "athena:StartQueryExecution",
                    "athena:GetQueryExecution",
                    "athena:GetQueryResults",
                    "athena:StopQueryExecution",
                    "athena:GetWorkGroup"
                ],
                resources=[
                    f"arn:aws:athena:{self.region}:{self.account}:workgroup/{self.athena_workgroup.name}"
                ]
            )
        )
        
        # Grant Glue Data Catalog permissions
        self.athena_query_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "glue:GetDatabase",
                    "glue:GetTable",
                    "glue:GetTables",
                    "glue:GetPartition",
                    "glue:GetPartitions"
                ],
                resources=[
                    f"arn:aws:glue:{self.region}:{self.account}:catalog",
                    f"arn:aws:glue:{self.region}:{self.account}:database/{self.glue_database.ref}",
                    f"arn:aws:glue:{self.region}:{self.account}:table/{self.glue_database.ref}/*"
                ]
            )
        )
        
        # Grant S3 permissions for data access and query results
        self.raw_data_bucket.grant_read(self.athena_query_role)
        self.processed_data_bucket.grant_read(self.athena_query_role)
        query_results_bucket.grant_read_write(self.athena_query_role)