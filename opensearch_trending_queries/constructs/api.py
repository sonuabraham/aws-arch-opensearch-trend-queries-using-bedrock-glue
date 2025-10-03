"""
API Construct - API Gateway and Lambda handlers for trending queries API
"""
from aws_cdk import (
    Duration,
    RemovalPolicy,
    aws_apigateway as apigw,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_logs as logs,
    aws_dynamodb as dynamodb,
)
from constructs import Construct
from ..config.environment_config import EnvironmentConfig
import os


class ApiConstruct(Construct):
    """Construct for API Gateway and Lambda API handlers"""
    
    def __init__(
        self, 
        scope: Construct, 
        construct_id: str, 
        config: EnvironmentConfig,
        trending_queries_table: dynamodb.Table,
        api_lambda_role: iam.Role = None,
        logs_kms_key = None
    ):
        super().__init__(scope, construct_id)
        
        self.config = config
        self.trending_queries_table = trending_queries_table
        self.api_lambda_role = api_lambda_role
        self.logs_kms_key = logs_kms_key
        
        # Create Lambda functions for API handlers
        self._create_api_lambda_functions()
        
        # Create API Gateway REST API
        self._create_api_gateway()
        
        # Configure API resources and methods
        self._configure_api_resources()
    
    def _create_api_lambda_functions(self) -> None:
        """Create Lambda functions for API endpoints"""
        
        # Get Lambda configuration
        timeout_seconds = self.config.get("lambda", "timeout_seconds")
        memory_mb = self.config.get("lambda", "memory_mb")
        
        # Create CloudWatch log group for Lambda functions with encryption
        log_group_kwargs = {
            "log_group_name": f"/aws/lambda/{self.config.resource_prefix}-api",
            "retention": logs.RetentionDays.TWO_WEEKS,
            "removal_policy": RemovalPolicy.DESTROY
        }
        
        # Add KMS encryption if available
        if self.logs_kms_key:
            log_group_kwargs["encryption_key"] = self.logs_kms_key
        
        self.api_log_group = logs.LogGroup(self, "ApiLambdaLogGroup", **log_group_kwargs)
        
        # Use provided role or create fallback role
        if not self.api_lambda_role:
            # Create IAM role for API Lambda functions
            self.api_lambda_role = iam.Role(
                self, "ApiLambdaRole",
                role_name=f"{self.config.resource_prefix}-api-lambda",
                assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
                description="Role for API Lambda functions",
                managed_policies=[
                    iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
                ]
            )
            
            # Grant DynamoDB read permissions
            self.trending_queries_table.grant_read_data(self.api_lambda_role)
            
            # Grant CloudWatch metrics permissions
            self.api_lambda_role.add_to_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "cloudwatch:PutMetricData"
                    ],
                    resources=["*"]
                )
            )
            
            # Enable X-Ray tracing permissions
            self.api_lambda_role.add_to_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "xray:PutTraceSegments",
                        "xray:PutTelemetryRecords"
                    ],
                    resources=["*"]
                )
            )
        
        # Common environment variables for API Lambda functions
        common_env = {
            "TABLE_NAME": self.trending_queries_table.table_name,
            "REGION": self.config.config.get("region", "us-east-1"),
            "LOG_LEVEL": "INFO" if self.config.is_production else "DEBUG"
        }
        
        # Create Lambda function for GET /trending-queries endpoint
        self.get_trending_queries_function = lambda_.Function(
            self, "GetTrendingQueriesFunction",
            function_name=f"{self.config.resource_prefix}-get-trending-queries",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="get_trending_queries.lambda_handler",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "..", "lambda")
            ),
            role=self.api_lambda_role,
            timeout=Duration.seconds(30),  # API endpoints should be fast
            memory_size=memory_mb,
            environment=common_env,
            log_group=self.api_log_group,
            description="Retrieves current trending queries from DynamoDB",
            tracing=lambda_.Tracing.ACTIVE  # Enable X-Ray tracing
        )
        
        # Create Lambda function for GET /trending-queries/{date} endpoint
        self.get_trending_queries_by_date_function = lambda_.Function(
            self, "GetTrendingQueriesByDateFunction",
            function_name=f"{self.config.resource_prefix}-get-trending-queries-by-date",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="get_trending_queries_by_date.lambda_handler",
            code=lambda_.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "..", "lambda")
            ),
            role=self.api_lambda_role,
            timeout=Duration.seconds(30),
            memory_size=memory_mb,
            environment=common_env,
            log_group=self.api_log_group,
            description="Retrieves historical trending queries by date from DynamoDB",
            tracing=lambda_.Tracing.ACTIVE
        )
    
    def _create_api_gateway(self) -> None:
        """Create API Gateway REST API with authentication and authorization"""
        
        # Get API Gateway configuration
        throttle_rate_limit = self.config.get("api_gateway", "throttle_rate_limit")
        throttle_burst_limit = self.config.get("api_gateway", "throttle_burst_limit")
        
        # Create CloudWatch log group for API Gateway with encryption
        log_group_kwargs = {
            "log_group_name": f"/aws/apigateway/{self.config.resource_prefix}",
            "retention": logs.RetentionDays.ONE_WEEK,
            "removal_policy": RemovalPolicy.DESTROY
        }
        
        # Add KMS encryption if available
        if self.logs_kms_key:
            log_group_kwargs["encryption_key"] = self.logs_kms_key
        
        self.api_gateway_log_group = logs.LogGroup(self, "ApiGatewayLogGroup", **log_group_kwargs)
        
        # Create API Gateway REST API
        self.api_gateway = apigw.RestApi(
            self, "TrendingQueriesApi",
            rest_api_name=f"{self.config.resource_prefix}-api",
            description="API for accessing trending search queries",
            deploy_options=apigw.StageOptions(
                stage_name=self.config.env_name,
                throttling_rate_limit=throttle_rate_limit,
                throttling_burst_limit=throttle_burst_limit,
                logging_level=apigw.MethodLoggingLevel.INFO,
                access_log_destination=apigw.LogGroupLogDestination(self.api_gateway_log_group),
                access_log_format=apigw.AccessLogFormat.json_with_standard_fields(
                    caller=True,
                    http_method=True,
                    ip=True,
                    protocol=True,
                    request_time=True,
                    resource_path=True,
                    response_length=True,
                    status=True,
                    user=True
                ),
                tracing_enabled=True,  # Enable X-Ray tracing
                metrics_enabled=True,
                data_trace_enabled=not self.config.is_production  # Only in non-prod
            ),
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS if not self.config.is_production else ["https://example.com"],
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=[
                    "Content-Type",
                    "X-Amz-Date",
                    "Authorization",
                    "X-Api-Key",
                    "X-Amz-Security-Token"
                ],
                allow_credentials=True,
                max_age=Duration.hours(1)
            ),
            endpoint_types=[apigw.EndpointType.REGIONAL],
            cloud_watch_role=True
        )
        
        # Create API key for authentication
        self.api_key = self.api_gateway.add_api_key(
            "ApiKey",
            api_key_name=f"{self.config.resource_prefix}-api-key",
            description="API key for trending queries API"
        )
        
        # Create usage plan
        self.usage_plan = self.api_gateway.add_usage_plan(
            "UsagePlan",
            name=f"{self.config.resource_prefix}-usage-plan",
            description="Usage plan for trending queries API",
            throttle=apigw.ThrottleSettings(
                rate_limit=throttle_rate_limit,
                burst_limit=throttle_burst_limit
            ),
            quota=apigw.QuotaSettings(
                limit=100000 if self.config.is_production else 10000,
                period=apigw.Period.DAY
            )
        )
        
        # Associate API key with usage plan
        self.usage_plan.add_api_key(self.api_key)
        
        # Add API stage to usage plan
        self.usage_plan.add_api_stage(
            stage=self.api_gateway.deployment_stage
        )
    
    def _configure_api_resources(self) -> None:
        """Configure API resources and methods"""
        
        # Create request/response models
        self._create_api_models()
        
        # Create request validators
        request_validator = self.api_gateway.add_request_validator(
            "RequestValidator",
            request_validator_name=f"{self.config.resource_prefix}-request-validator",
            validate_request_body=True,
            validate_request_parameters=True
        )
        
        # Create /trending-queries resource
        trending_queries_resource = self.api_gateway.root.add_resource("trending-queries")
        
        # Configure GET /trending-queries endpoint
        self._configure_get_trending_queries_endpoint(
            trending_queries_resource,
            request_validator
        )
        
        # Create /trending-queries/{date} resource
        date_resource = trending_queries_resource.add_resource("{date}")
        
        # Configure GET /trending-queries/{date} endpoint
        self._configure_get_trending_queries_by_date_endpoint(
            date_resource,
            request_validator
        )
    
    def _create_api_models(self) -> None:
        """Create request/response models for API validation"""
        
        # Response model for trending query item
        self.trending_query_model = self.api_gateway.add_model(
            "TrendingQueryModel",
            model_name="TrendingQuery",
            content_type="application/json",
            schema=apigw.JsonSchema(
                schema=apigw.JsonSchemaVersion.DRAFT4,
                title="TrendingQuery",
                type=apigw.JsonSchemaType.OBJECT,
                properties={
                    "query": apigw.JsonSchema(type=apigw.JsonSchemaType.STRING),
                    "rank": apigw.JsonSchema(type=apigw.JsonSchemaType.INTEGER),
                    "count": apigw.JsonSchema(type=apigw.JsonSchemaType.INTEGER),
                    "growth_rate": apigw.JsonSchema(type=apigw.JsonSchemaType.NUMBER),
                    "category": apigw.JsonSchema(type=apigw.JsonSchemaType.STRING),
                    "cluster_id": apigw.JsonSchema(type=apigw.JsonSchemaType.STRING)
                },
                required=["query", "rank", "count"]
            )
        )
        
        # Response model for trending queries list
        self.trending_queries_response_model = self.api_gateway.add_model(
            "TrendingQueriesResponseModel",
            model_name="TrendingQueriesResponse",
            content_type="application/json",
            schema=apigw.JsonSchema(
                schema=apigw.JsonSchemaVersion.DRAFT4,
                title="TrendingQueriesResponse",
                type=apigw.JsonSchemaType.OBJECT,
                properties={
                    "date": apigw.JsonSchema(type=apigw.JsonSchemaType.STRING),
                    "trending_queries": apigw.JsonSchema(
                        type=apigw.JsonSchemaType.ARRAY,
                        items=apigw.JsonSchema(ref=f"#/definitions/{self.trending_query_model.model_id}")
                    ),
                    "next_token": apigw.JsonSchema(type=apigw.JsonSchemaType.STRING)
                },
                required=["date", "trending_queries"]
            )
        )
        
        # Error response model
        self.error_response_model = self.api_gateway.add_model(
            "ErrorResponseModel",
            model_name="ErrorResponse",
            content_type="application/json",
            schema=apigw.JsonSchema(
                schema=apigw.JsonSchemaVersion.DRAFT4,
                title="ErrorResponse",
                type=apigw.JsonSchemaType.OBJECT,
                properties={
                    "error": apigw.JsonSchema(type=apigw.JsonSchemaType.STRING),
                    "message": apigw.JsonSchema(type=apigw.JsonSchemaType.STRING)
                },
                required=["error", "message"]
            )
        )
    
    def _configure_get_trending_queries_endpoint(
        self,
        resource: apigw.Resource,
        request_validator: apigw.RequestValidator
    ) -> None:
        """Configure GET /trending-queries endpoint"""
        
        # Create Lambda integration
        integration = apigw.LambdaIntegration(
            self.get_trending_queries_function,
            proxy=False,
            integration_responses=[
                apigw.IntegrationResponse(
                    status_code="200",
                    response_templates={
                        "application/json": ""
                    }
                ),
                apigw.IntegrationResponse(
                    status_code="400",
                    selection_pattern=".*\\[BadRequest\\].*",
                    response_templates={
                        "application/json": '{"error": "BadRequest", "message": $input.path(\'$.errorMessage\')}'
                    }
                ),
                apigw.IntegrationResponse(
                    status_code="500",
                    selection_pattern=".*\\[InternalError\\].*",
                    response_templates={
                        "application/json": '{"error": "InternalError", "message": "An internal error occurred"}'
                    }
                )
            ],
            request_templates={
                "application/json": '{"limit": "$input.params(\'limit\')", "next_token": "$input.params(\'next_token\')"}'
            }
        )
        
        # Add GET method
        resource.add_method(
            "GET",
            integration,
            api_key_required=True,
            request_validator=request_validator,
            request_parameters={
                "method.request.querystring.limit": False,
                "method.request.querystring.next_token": False
            },
            method_responses=[
                apigw.MethodResponse(
                    status_code="200",
                    response_models={
                        "application/json": self.trending_queries_response_model
                    }
                ),
                apigw.MethodResponse(
                    status_code="400",
                    response_models={
                        "application/json": self.error_response_model
                    }
                ),
                apigw.MethodResponse(
                    status_code="500",
                    response_models={
                        "application/json": self.error_response_model
                    }
                )
            ]
        )
    
    def _configure_get_trending_queries_by_date_endpoint(
        self,
        resource: apigw.Resource,
        request_validator: apigw.RequestValidator
    ) -> None:
        """Configure GET /trending-queries/{date} endpoint"""
        
        # Create Lambda integration
        integration = apigw.LambdaIntegration(
            self.get_trending_queries_by_date_function,
            proxy=False,
            integration_responses=[
                apigw.IntegrationResponse(
                    status_code="200",
                    response_templates={
                        "application/json": ""
                    }
                ),
                apigw.IntegrationResponse(
                    status_code="400",
                    selection_pattern=".*\\[BadRequest\\].*",
                    response_templates={
                        "application/json": '{"error": "BadRequest", "message": $input.path(\'$.errorMessage\')}'
                    }
                ),
                apigw.IntegrationResponse(
                    status_code="404",
                    selection_pattern=".*\\[NotFound\\].*",
                    response_templates={
                        "application/json": '{"error": "NotFound", "message": "No trending queries found for the specified date"}'
                    }
                ),
                apigw.IntegrationResponse(
                    status_code="500",
                    selection_pattern=".*\\[InternalError\\].*",
                    response_templates={
                        "application/json": '{"error": "InternalError", "message": "An internal error occurred"}'
                    }
                )
            ],
            request_templates={
                "application/json": '{"date": "$input.params(\'date\')", "limit": "$input.params(\'limit\')", "next_token": "$input.params(\'next_token\')"}'
            }
        )
        
        # Add GET method
        resource.add_method(
            "GET",
            integration,
            api_key_required=True,
            request_validator=request_validator,
            request_parameters={
                "method.request.path.date": True,
                "method.request.querystring.limit": False,
                "method.request.querystring.next_token": False
            },
            method_responses=[
                apigw.MethodResponse(
                    status_code="200",
                    response_models={
                        "application/json": self.trending_queries_response_model
                    }
                ),
                apigw.MethodResponse(
                    status_code="400",
                    response_models={
                        "application/json": self.error_response_model
                    }
                ),
                apigw.MethodResponse(
                    status_code="404",
                    response_models={
                        "application/json": self.error_response_model
                    }
                ),
                apigw.MethodResponse(
                    status_code="500",
                    response_models={
                        "application/json": self.error_response_model
                    }
                )
            ]
        )
