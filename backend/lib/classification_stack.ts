import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as iam from 'aws-cdk-lib/aws-iam';

export class ForestClassificationStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Define CloudFormation parameters without default values
    const assetsBucketNameParam = new cdk.CfnParameter(this, 'AssetsBucketName', {
      type: 'String',
      description: 'The name of the S3 bucket containing Lambda layers and function code.',
    });

    const bucketNameParam = new cdk.CfnParameter(this, 'BucketName', {
      type: 'String',
      description: 'The name of the S3 bucket to store input/output files. Must be globally unique.',
    });

    const geeCredentialsFileParam = new cdk.CfnParameter(this, 'GeeCredentialsFile', {
      type: 'String',
      description: 'Name of the Google Earth Engine credentials file in the S3 bucket (e.g., credentials/custom-gee-credentials.json)',
    });

    // Use parameter values
    const assetsBucketName = assetsBucketNameParam.valueAsString;
    const bucketName = bucketNameParam.valueAsString;
    const geeCredentialsFile = geeCredentialsFileParam.valueAsString;

    // Reference the assets bucket
    const assetsBucket = s3.Bucket.fromBucketName(this, 'AssetsBucket', assetsBucketName);

    // Create an S3 bucket for storing input/output files
    const bucket = new s3.Bucket(this, 'ForestClassificationBucket', {
      bucketName: bucketName,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      cors: [{
        allowedOrigins: ['*'],
        allowedMethods: [s3.HttpMethods.GET, s3.HttpMethods.PUT],
        allowedHeaders: ['*'],
        exposedHeaders: [],      // optional
        maxAge: 3600             // optional
      }]
    });

    // Create the Lambda function layers with fixed S3 keys
    const earthEngineLayer = new lambda.LayerVersion(this, 'EarthEngineLayer', {
      code: lambda.Code.fromBucket(assetsBucket, 'layers/earth_engine_layer.zip'),
      compatibleRuntimes: [lambda.Runtime.PYTHON_3_13],
      description: 'Earth Engine API and dependencies',
    });

    const imageProcessingLayer = new lambda.LayerVersion(this, 'ImageProcessingLayer', {
      code: lambda.Code.fromBucket(assetsBucket, 'layers/image_processing.zip'),
      compatibleRuntimes: [lambda.Runtime.PYTHON_3_13],
      description: 'PIL, Shapely, and other image processing libraries',
    });

    // Create the Lambda function using code from S3 with fixed S3 key
    const forestClassificationLambda = new lambda.Function(this, 'ForestClassificationLambda', {
      runtime: lambda.Runtime.PYTHON_3_13,
      handler: 'lambda_function.lambda_handler',
      code: lambda.Code.fromBucket(assetsBucket, 'lambda-function-code.zip'),
      memorySize: 10240,
      timeout: cdk.Duration.seconds(900),
      environment: {
        S3_BUCKET: bucket.bucketName,
        ASSETS_BUCKET: assetsBucketName,
        EE_KEY_S3_KEY: geeCredentialsFile,
        EE_KEY_PATH: '/tmp/ee-key.json',
        DATA_PATH: '/tmp/data.json',
        OUTPUT_PREFIX: 'forest_classification',
        UPLOAD_EXPIRATION: '3600',
        DOWNLOAD_EXPIRATION: '86400',
        ALLOWED_ORIGINS: '*',
        DEBUG: 'false',
      },
      layers: [earthEngineLayer, imageProcessingLayer],
    });

    const functionUrl = forestClassificationLambda.addFunctionUrl({
      authType: lambda.FunctionUrlAuthType.NONE, // Public access; use AWS_IAM for IAM-based auth if needed
    });

    // Grant the Lambda function permissions to read/write to the S3 bucket
    bucket.grantReadWrite(forestClassificationLambda);

    // Grant the Lambda function permissions to read from the assets bucket
    assetsBucket.grantRead(forestClassificationLambda);

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
      description: 'The name of the S3 bucket for input/output files',
    });

    new cdk.CfnOutput(this, 'UploadInstruction', {
      value: `Upload your data files to s3://${bucket.bucketName}/uploads/ and ensure the GEE credentials file is at s3://${bucket.bucketName}/${geeCredentialsFile}`,
      description: 'Instructions for using the S3 bucket',
    });

    new cdk.CfnOutput(this, 'LambdaFunctionUrl', {
      value: functionUrl.url,
      description: 'The URL of the Forest Classification Lambda function for front-end integration',
    });
    
  }
}