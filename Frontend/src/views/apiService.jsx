const API_URL = process.env.REACT_APP_API_URL;

//uploading the json file
export const initiateUpload = async (filename) => {
  console.log('Calling:', API_URL);
  const res = await fetch(API_URL, {
    method: 'POST',
    body: JSON.stringify({ operation: 'upload', filename }),
  });
  
  if (!res.ok) {
    throw new Error(`Upload initiation failed: ${res.status} ${res.statusText}`);
  }
  
  const data = await res.json();
  console.log('Upload done:', data);
  return data;
};

//uploading url in s3 bucket
export const uploadToS3 = async (uploadUrl, file) => {
  try {
    const res = await fetch(uploadUrl, {
      method: 'PUT',
      body: file
    });
    
    console.log("S3 response status:", res.status);
    const responseText = await res.text();
    console.log("S3 response text:", responseText);
    
    if (responseText && responseText.trim().startsWith('{')) {
      try {
        const data = JSON.parse(responseText);
        console.log("S3 parsed response:", data);
        
        if (data.status === "error") {
          throw new Error(data.message || "An error occurred during upload");
        }
        return data;
      } catch (parseError) {
        console.error("Error parsing JSON response:", parseError);
        if (responseText.includes("error") || responseText.includes("failed")) {
          throw new Error(responseText || "An error occurred during upload");
        }
      }
    }
    
  
    if (!res.ok) {
      throw new Error(`S3 upload failed: ${res.status} ${res.statusText}`);
    }
    
    console.log("S3 success");
    return { status: "success" };
  } catch (error) {
    console.error("Error in uploadToS3:", error);
    throw error;
  }
};

//analyzing operation
export const analyze = async ({ filename, startDate, endDate, outputPrefix }) => {
  try {
    console.log("Analyze request payload:", {
      operation: 'analysis',
      filename,
      start_date: endDate,
      end_date: startDate,
      output_prefix: outputPrefix
    });
  
    const res = await fetch(API_URL, {
      method: 'POST',
      body: JSON.stringify({
        operation: 'analysis',
        filename,
        start_date: endDate,
        end_date: startDate,
        output_prefix: outputPrefix
      })
    });
    
    console.log("Analyze response status:", res.status);
    
    const responseText = await res.text();
    console.log("Analyze response text:", responseText);
    
    
    let data;
    try {
      data = JSON.parse(responseText);
      console.log("Analyze parsed response:", data);
    } catch (e) {
      console.error("Error parsing analyze response:", e);
      throw new Error(`Analysis failed: Could not parse response`);
    }
    
   
    if (data && data.status === "error") {
      console.error("Analysis error from server:", data.message);
      return data; 
    }
    
    if (!res.ok) {
      throw new Error(`Analysis failed: ${res.status} ${res.statusText}`);
    }
    
    return data; 
  } catch (error) {
    console.error("Error in analyze function:", error);
    throw error;
  }
};