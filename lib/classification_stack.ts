import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as s3deploy from 'aws-cdk-lib/aws-s3-deployment';
import * as path from 'path';

export class ForestClassificationStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Define CloudFormation parameters
    const bucketNameParam = new cdk.CfnParameter(this, 'BucketName', {
      type: 'String',
      description: 'The name of the S3 bucket to store input/output files. Must be globally unique.',
    });

    const geeServiceAccountParam = new cdk.CfnParameter(this, 'GeeServiceAccount', {
      type: 'String',
      description: 'Google Earth Engine service account email (e.g., your-account@your-project.iam.gserviceaccount.com)',
    });

    const geeCredentialsFileParam = new cdk.CfnParameter(this, 'GeeCredentialsFile', {
      type: 'String',
      description: 'Name of the Google Earth Engine credentials file to upload to S3 (e.g., my-gee-credentials.json)',
    });

    // Use parameter values
    const bucketName = bucketNameParam.valueAsString;
    const geeServiceAccount = geeServiceAccountParam.valueAsString;
    const geeCredentialsFile = geeCredentialsFileParam.valueAsString;

    // Create an S3 bucket for storing input/output files
    const bucket = new s3.Bucket(this, 'ForestClassificationBucket', {
      bucketName: bucketName,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
    });

    // Upload gee-credentials.json to the S3 bucket
    new s3deploy.BucketDeployment(this, 'UploadGeeCredentials', {
      sources: [s3deploy.Source.asset('./credentials')],
      destinationBucket: bucket,
      destinationKeyPrefix: '',
    });

    // Create the Lambda function layers
    const earthEngineLayer = new lambda.LayerVersion(this, 'EarthEngineLayer', {
        code: lambda.Code.fromAsset(path.join(__dirname, '..','layers', 'earth_engine_layer.zip')),
        compatibleRuntimes: [lambda.Runtime.PYTHON_3_9],
        description: 'Earth Engine API and dependencies',
      });
  
    const imageProcessingLayer = new lambda.LayerVersion(this, 'ImageProcessingLayer', {
    code: lambda.Code.fromAsset(path.join(__dirname, '..','layers', 'image_processing.zip')),
    compatibleRuntimes: [lambda.Runtime.PYTHON_3_9],
    description: 'PIL, Shapely, and other image processing libraries',
    });

    // Create the Lambda function using local assets
    const forestClassificationLambda = new lambda.Function(this, 'ForestClassificationLambda', {
      runtime: lambda.Runtime.PYTHON_3_9,
      handler: 'lambda_function.lambda_handler',
      code: lambda.Code.fromAsset('lambda'),
      memorySize: 10240,
      timeout: cdk.Duration.seconds(900),
      environment: {
        S3_BUCKET: bucket.bucketName,
        SERVICE_ACCOUNT: geeServiceAccount,
        EE_KEY_S3_KEY: geeCredentialsFile,
        EE_KEY_PATH: '/tmp/ee-key.json',
        DATA_PATH: '/tmp/data.json',
        DEFAULT_START_DATE: '2023-06-01',
        DEFAULT_END_DATE: '2024-07-30',
        DEFAULT_OUTPUT_PREFIX: 'forest_classification',
        UPLOAD_EXPIRATION: '3600',
        DOWNLOAD_EXPIRATION: '86400',
        ALLOWED_ORIGINS: '*',
        DEBUG: 'false',
      },
      layers: [earthEngineLayer, imageProcessingLayer],
    });

    // Grant the Lambda function permissions to read/write to the S3 bucket
    bucket.grantReadWrite(forestClassificationLambda);

    // Grant the Lambda function permissions to write logs
    forestClassificationLambda.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ['logs:CreateLogGroup', 'logs:CreateLogStream', 'logs:PutLogEvents'],
        resources: [`arn:aws:logs:${this.region}:${this.account}:log-group:/aws/lambda/*:*`],
      })
    );

    // Output the Lambda function ARN, S3 bucket name, and instructions
    new cdk.CfnOutput(this, 'LambdaFunctionArn', {
      value: forestClassificationLambda.functionArn,
      description: 'The ARN of the Forest Classification Lambda function',
    });

    new cdk.CfnOutput(this, 'S3BucketName', {
      value: bucket.bucketName,
      description: 'The name of the S3 bucket',
    });

    new cdk.CfnOutput(this, 'UploadInstruction', {
      value: `Gee-credentials.json has been uploaded to s3://${bucket.bucketName}/${geeCredentialsFile}`,
      description: 'Confirmation of GEE credentials upload',
    });
  }
}