const AWS = require('aws-sdk');
const s3 = new AWS.S3();

exports.handler = async (event, context) => {
  const requestType = event.RequestType;
  const { BucketName, FileKey, FileContent } = event.ResourceProperties;

  try {
    if (requestType === 'Create' || requestType === 'Update') {
      // Upload the file to S3
      await s3.putObject({
        Bucket: BucketName,
        Key: FileKey,
        Body: FileContent,
      }).promise();

      return {
        Status: 'SUCCESS',
        Reason: 'File uploaded successfully',
        PhysicalResourceId: `${BucketName}/${FileKey}`,
        Data: {},
      };
    } else if (requestType === 'Delete') {
      // Optionally delete the file from S3 on stack deletion
      await s3.deleteObject({
        Bucket: BucketName,
        Key: FileKey,
      }).promise();

      return {
        Status: 'SUCCESS',
        Reason: 'File deleted successfully',
        PhysicalResourceId: `${BucketName}/${FileKey}`,
      };
    }
  } catch (error) {
    return {
      Status: 'FAILED',
      Reason: error.message,
      PhysicalResourceId: context.logStreamName,
    };
  }
};