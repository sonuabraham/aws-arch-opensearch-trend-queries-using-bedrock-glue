#!/usr/bin/env python3
"""
CDK Deployment Script for OpenSearch Trending Queries
Handles environment-specific deployments with validation and rollback capabilities
"""
import argparse
import subprocess
import sys
import json
import os
from typing import List, Optional, Dict, Any


class CDKDeployer:
    """Handles CDK deployment operations with validation and error handling"""
    
    VALID_ENVIRONMENTS = ["dev", "staging", "prod"]
    STACK_DEPENDENCIES = {
        "OpenSearchTrendingQueries": []  # Main stack has no dependencies
    }
    
    def __init__(self, environment: str, region: str = "us-east-1", profile: Optional[str] = None):
        self.environment = environment
        self.region = region
        self.profile = profile
        self.validate_environment()
    
    def validate_environment(self) -> None:
        """Validate that the environment is valid"""
        if self.environment not in self.VALID_ENVIRONMENTS:
            raise ValueError(
                f"Invalid environment: {self.environment}. "
                f"Must be one of: {', '.join(self.VALID_ENVIRONMENTS)}"
            )
    
    def _build_cdk_command(self, command: str, additional_args: List[str] = None) -> List[str]:
        """Build CDK command with common arguments"""
        cmd = ["cdk", command]
        
        # Add context for environment
        cmd.extend(["-c", f"env={self.environment}"])
        
        # Add profile if specified
        if self.profile:
            cmd.extend(["--profile", self.profile])
        
        # Add region
        cmd.extend(["--region", self.region])
        
        # Add additional arguments
        if additional_args:
            cmd.extend(additional_args)
        
        return cmd
    
    def _run_command(self, cmd: List[str], check: bool = True) -> subprocess.CompletedProcess:
        """Run a command and handle errors"""
        print(f"Running: {' '.join(cmd)}")
        try:
            result = subprocess.run(
                cmd,
                check=check,
                capture_output=True,
                text=True
            )
            if result.stdout:
                print(result.stdout)
            return result
        except subprocess.CalledProcessError as e:
            print(f"Error running command: {e}", file=sys.stderr)
            if e.stderr:
                print(e.stderr, file=sys.stderr)
            raise
    
    def bootstrap(self) -> None:
        """Bootstrap CDK in the target account/region"""
        print(f"Bootstrapping CDK in region {self.region}...")
        cmd = self._build_cdk_command("bootstrap")
        self._run_command(cmd)
        print("Bootstrap complete!")
    
    def synth(self) -> None:
        """Synthesize CloudFormation templates"""
        print(f"Synthesizing CDK stack for {self.environment}...")
        cmd = self._build_cdk_command("synth")
        self._run_command(cmd)
        print("Synthesis complete!")
    
    def diff(self) -> None:
        """Show differences between deployed stack and local changes"""
        print(f"Showing diff for {self.environment}...")
        cmd = self._build_cdk_command("diff")
        # Don't check return code as diff returns non-zero when there are differences
        self._run_command(cmd, check=False)
    
    def deploy(self, require_approval: bool = True, hotswap: bool = False) -> None:
        """Deploy the CDK stack"""
        print(f"Deploying to {self.environment} environment...")
        
        # Pre-deployment validation
        self._validate_deployment()
        
        # Build deploy command
        additional_args = []
        if not require_approval:
            additional_args.append("--require-approval=never")
        if hotswap:
            additional_args.append("--hotswap")
        
        # Add outputs file
        outputs_file = f"cdk-outputs-{self.environment}.json"
        additional_args.extend(["--outputs-file", outputs_file])
        
        cmd = self._build_cdk_command("deploy", additional_args)
        
        try:
            self._run_command(cmd)
            print(f"Deployment to {self.environment} complete!")
            print(f"Outputs saved to: {outputs_file}")
            
            # Post-deployment validation
            self._validate_post_deployment()
            
        except subprocess.CalledProcessError as e:
            print(f"Deployment failed! Error: {e}", file=sys.stderr)
            self._handle_deployment_failure()
            raise
    
    def destroy(self, force: bool = False) -> None:
        """Destroy the CDK stack"""
        if self.environment == "prod" and not force:
            response = input(
                "WARNING: You are about to destroy the PRODUCTION stack. "
                "Type 'DELETE' to confirm: "
            )
            if response != "DELETE":
                print("Destruction cancelled.")
                return
        
        print(f"Destroying {self.environment} stack...")
        additional_args = ["--force"] if force else []
        cmd = self._build_cdk_command("destroy", additional_args)
        self._run_command(cmd)
        print("Stack destroyed!")
    
    def _validate_deployment(self) -> None:
        """Pre-deployment validation checks"""
        print("Running pre-deployment validation...")
        
        # Check if AWS credentials are configured
        try:
            result = subprocess.run(
                ["aws", "sts", "get-caller-identity"],
                capture_output=True,
                text=True,
                check=True
            )
            identity = json.loads(result.stdout)
            print(f"Deploying as: {identity.get('Arn')}")
        except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
            raise RuntimeError("AWS credentials not configured or invalid") from e
        
        # Synthesize to validate template
        print("Validating CloudFormation template...")
        self.synth()
        
        print("Pre-deployment validation passed!")
    
    def _validate_post_deployment(self) -> None:
        """Post-deployment validation checks"""
        print("Running post-deployment validation...")
        
        stack_name = f"OpenSearchTrendingQueries-{self.environment}"
        
        # Check stack status
        try:
            cmd = [
                "aws", "cloudformation", "describe-stacks",
                "--stack-name", stack_name,
                "--region", self.region
            ]
            if self.profile:
                cmd.extend(["--profile", self.profile])
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            stacks = json.loads(result.stdout).get("Stacks", [])
            
            if stacks:
                status = stacks[0].get("StackStatus")
                if status in ["CREATE_COMPLETE", "UPDATE_COMPLETE"]:
                    print(f"Stack status: {status} ✓")
                else:
                    print(f"Warning: Stack status is {status}")
            else:
                print("Warning: Stack not found")
                
        except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
            print(f"Warning: Could not validate stack status: {e}")
        
        print("Post-deployment validation complete!")
    
    def _handle_deployment_failure(self) -> None:
        """Handle deployment failures and provide rollback guidance"""
        print("\n" + "="*60)
        print("DEPLOYMENT FAILED")
        print("="*60)
        
        stack_name = f"OpenSearchTrendingQueries-{self.environment}"
        
        print(f"\nTo check stack events:")
        print(f"  aws cloudformation describe-stack-events --stack-name {stack_name}")
        
        print(f"\nTo rollback to previous version:")
        print(f"  aws cloudformation rollback-stack --stack-name {stack_name}")
        
        print(f"\nTo delete failed stack:")
        print(f"  cdk destroy -c env={self.environment}")
        
        print("\n" + "="*60)


def main():
    parser = argparse.ArgumentParser(
        description="Deploy OpenSearch Trending Queries CDK Stack"
    )
    parser.add_argument(
        "command",
        choices=["bootstrap", "synth", "diff", "deploy", "destroy"],
        help="CDK command to execute"
    )
    parser.add_argument(
        "--env",
        choices=CDKDeployer.VALID_ENVIRONMENTS,
        default="dev",
        help="Target environment (default: dev)"
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
        "--no-approval",
        action="store_true",
        help="Skip approval prompts during deployment"
    )
    parser.add_argument(
        "--hotswap",
        action="store_true",
        help="Attempt to update resources directly (faster, dev only)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force operation without confirmation"
    )
    
    args = parser.parse_args()
    
    # Validate hotswap is only used in dev
    if args.hotswap and args.env != "dev":
        print("Error: --hotswap can only be used with dev environment", file=sys.stderr)
        sys.exit(1)
    
    try:
        deployer = CDKDeployer(
            environment=args.env,
            region=args.region,
            profile=args.profile
        )
        
        if args.command == "bootstrap":
            deployer.bootstrap()
        elif args.command == "synth":
            deployer.synth()
        elif args.command == "diff":
            deployer.diff()
        elif args.command == "deploy":
            deployer.deploy(
                require_approval=not args.no_approval,
                hotswap=args.hotswap
            )
        elif args.command == "destroy":
            deployer.destroy(force=args.force)
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
