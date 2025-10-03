"""
Data Ingestion Construct - Kinesis Data Streams and S3 integration
"""
from aws_cdk import (
    Duration,
    RemovalPolicy,
    aws_kinesis as kinesis,
    aws_s3 as s3,
    aws_iam as iam,
    aws_kms as kms,
    aws_kinesisfirehose as firehose,
    aws_logs as logs,
)
from constructs import Construct
from ..config.environment_config import EnvironmentConfig
from typing import Optional


class DataIngestionConstruct(Construct):
    """Construct for data ingestion components"""
    
    def __init__(
        self, 
        scope: Construct, 
        construct_id: str, 
        config: EnvironmentConfig, 
        raw_data_bucket: s3.Bucket,
        kinesis_kms_key: Optional[kms.Key] = None,
        logs_kms_key: Optional[kms.Key] = None,
        kinesis_producer_role: Optional[iam.Role] = None,
        firehose_delivery_role: Optional[iam.Role] = None
    ):
        super().__init__(scope, construct_id)
        
        self.config = config
        self.raw_data_bucket = raw_data_bucket
        self.kinesis_kms_key = kinesis_kms_key
        self.logs_kms_key = logs_kms_key
        self.kinesis_producer_role = kinesis_producer_role
        self.firehose_delivery_role = firehose_delivery_role
        
        # Create Kinesis Data Stream
        self._create_kinesis_stream()
        
        # Create IAM roles for stream access (if not provided)
        if not self.kinesis_producer_role or not self.firehose_delivery_role:
            self._create_iam_roles()
        
        # Create Kinesis Data Firehose for S3 delivery
        self._create_firehose_delivery_stream()
    
    def _create_kinesis_stream(self) -> None:
        """Create Kinesis Data Stream with auto-scaling configuration"""
        
        # Get configuration values
        shard_count = self.config.get("kinesis", "shard_count")
        retention_hours = self.config.get("kinesis", "retention_hours")
        
        # Determine encryption configuration
        if self.kinesis_kms_key:
            encryption_type = kinesis.StreamEncryption.KMS
            encryption_key = self.kinesis_kms_key
        else:
            encryption_type = kinesis.StreamEncryption.MANAGED
            encryption_key = None
        
        # Create the Kinesis Data Stream
        stream_kwargs = {
            "stream_name": f"{self.config.resource_prefix}-search-queries",
            "shard_count": shard_count,
            "retention_period": Duration.hours(retention_hours),
            "stream_mode": kinesis.StreamMode.PROVISIONED,
            "encryption": encryption_type
        }
        
        if encryption_key:
            stream_kwargs["encryption_key"] = encryption_key
        
        self.kinesis_stream = kinesis.Stream(self, "SearchQueryStream", **stream_kwargs)
    
    def _create_iam_roles(self) -> None:
        """Create IAM roles for Kinesis stream access (fallback if not provided by SecurityConstruct)"""
        
        if not self.kinesis_producer_role:
            # Role for applications to write to Kinesis
            self.kinesis_producer_role = iam.Role(
                self, "KinesisProducerRole",
                role_name=f"{self.config.resource_prefix}-kinesis-producer",
                assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
                description="Role for applications to write search query logs to Kinesis"
            )
            
            # Grant write permissions to Kinesis stream
            self.kinesis_stream.grant_write(self.kinesis_producer_role)
        
        if not self.firehose_delivery_role:
            # Role for Kinesis Data Firehose to read from stream and write to S3
            self.firehose_delivery_role = iam.Role(
                self, "FirehoseDeliveryRole",
                role_name=f"{self.config.resource_prefix}-firehose-delivery",
                assumed_by=iam.ServicePrincipal("firehose.amazonaws.com"),
                description="Role for Kinesis Data Firehose to deliver data to S3"
            )
            
            # Grant read permissions to Kinesis stream
            self.kinesis_stream.grant_read(self.firehose_delivery_role)
            
            # Grant write permissions to S3 bucket
            self.raw_data_bucket.grant_write(self.firehose_delivery_role)
    
    def _create_firehose_delivery_stream(self) -> None:
        """Create Kinesis Data Firehose delivery stream to S3"""
        
        # Create CloudWatch log group for Firehose with encryption
        log_group_kwargs = {
            "log_group_name": f"/aws/kinesisfirehose/{self.config.resource_prefix}-search-queries",
            "retention": logs.RetentionDays.ONE_WEEK,
            "removal_policy": RemovalPolicy.DESTROY
        }
        
        # Add KMS encryption if available
        if self.logs_kms_key:
            log_group_kwargs["encryption_key"] = self.logs_kms_key
        
        log_group = logs.LogGroup(self, "FirehoseLogGroup", **log_group_kwargs)
        
        log_stream = logs.LogStream(
            self, "FirehoseLogStream",
            log_group=log_group,
            log_stream_name="S3Delivery"
        )
        
        # Create the Firehose delivery stream
        self.firehose_delivery_stream = firehose.CfnDeliveryStream(
            self, "SearchQueryDeliveryStream",
            delivery_stream_name=f"{self.config.resource_prefix}-search-queries-delivery",
            delivery_stream_type="KinesisStreamAsSource",
            kinesis_stream_source_configuration=firehose.CfnDeliveryStream.KinesisStreamSourceConfigurationProperty(
                kinesis_stream_arn=self.kinesis_stream.stream_arn,
                role_arn=self.firehose_delivery_role.role_arn
            ),
            extended_s3_destination_configuration=firehose.CfnDeliveryStream.ExtendedS3DestinationConfigurationProperty(
                bucket_arn=self.raw_data_bucket.bucket_arn,
                role_arn=self.firehose_delivery_role.role_arn,
                prefix="search-queries/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/hour=!{timestamp:HH}/",
                error_output_prefix="errors/",
                buffering_hints=firehose.CfnDeliveryStream.BufferingHintsProperty(
                    size_in_m_bs=5,
                    interval_in_seconds=300
                ),
                compression_format="GZIP",
                data_format_conversion_configuration=firehose.CfnDeliveryStream.DataFormatConversionConfigurationProperty(
                    enabled=True,
                    output_format_configuration=firehose.CfnDeliveryStream.OutputFormatConfigurationProperty(
                        serializer=firehose.CfnDeliveryStream.SerializerProperty(
                            parquet_ser_de=firehose.CfnDeliveryStream.ParquetSerDeProperty()
                        )
                    ),
                    schema_configuration=firehose.CfnDeliveryStream.SchemaConfigurationProperty(
                        database_name="search_queries_db",
                        table_name="search_queries",
                        role_arn=self.firehose_delivery_role.role_arn
                    )
                ),
                cloud_watch_logging_options=firehose.CfnDeliveryStream.CloudWatchLoggingOptionsProperty(
                    enabled=True,
                    log_group_name=log_group.log_group_name,
                    log_stream_name=log_stream.log_stream_name
                ),
                processing_configuration=firehose.CfnDeliveryStream.ProcessingConfigurationProperty(
                    enabled=False
                )
            )
        )