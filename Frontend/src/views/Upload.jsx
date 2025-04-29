import React, { useState, useCallback, useEffect, useRef } from 'react';
import { useDropzone } from 'react-dropzone';
import { useHistory } from 'react-router-dom';
import { initiateUpload, uploadToS3, analyze } from './apiService';
import ErrorModal from './ErrorModal'; 

const OpenEarthUpload = () => {
  const [files, setFiles] = useState([]);
  const [selectedFileName, setSelectedFileName] = useState('');
  const [isRotating, setIsRotating] = useState(true);
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState(''); 
  
  const history = useHistory();
  const endDateInputRef = useRef(null);
  
  useEffect(() => {
    const { state } = history.location;
    if (state && state.error) {
      alert(state.error);
    }  
    sessionStorage.removeItem('uploadComplete');  
    if (state && state.keepFile && state.selectedFile) {
      setFiles([state.selectedFile]);
      setSelectedFileName(state.selectedFile.name);
    }      
    const removeErrorNotifications = () => {
      document.querySelectorAll('div[style*="position: fixed"][style*="bottom"][style*="background-color: red"]')
        .forEach(el => el.remove());
    };    
    removeErrorNotifications();
    const interval = setInterval(removeErrorNotifications, 1000);
    return () => clearInterval(interval);
  }, [history]);
  
  // Date handling utilities
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  
  const formatDate = (date) => {
    return date.toISOString().split('T')[0];
  };

  const todayFormatted = formatDate(today);
  
  const getOneWeekBefore = (dateStr) => {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    const oneWeekBefore = new Date(date);
    oneWeekBefore.setDate(date.getDate() - 7);
    return formatDate(oneWeekBefore);
  };
  
  // File upload handling
  const onDrop = useCallback((acceptedFiles) => {
    setFiles(acceptedFiles);
    if (acceptedFiles.length > 0) {
      setSelectedFileName(acceptedFiles[0].name);
    }
  }, []);
  
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/json': ['.json', '.geojson']
    },
    noDragEventsBubbling: true
  });
  
  // Date validation effect
  useEffect(() => {
    if (startDate && endDateInputRef.current) {
      const startDateObj = new Date(startDate);
      startDateObj.setHours(0, 0, 0, 0);
      
      const sevenDaysBefore = new Date(startDateObj);
      sevenDaysBefore.setDate(startDateObj.getDate() - 7);
      sevenDaysBefore.setHours(0, 0, 0, 0);
      
      const handleDateInputChange = (e) => {
        const selectedDate = new Date(e.target.value);
        selectedDate.setHours(0, 0, 0, 0); 
        
        if (selectedDate.getTime() >= sevenDaysBefore.getTime()) {
          e.target.setCustomValidity("Please select a date before the 7-day window");
        } else {
          e.target.setCustomValidity("");
        }
      };
      
      const endDateElement = endDateInputRef.current;
      endDateElement.addEventListener('input', handleDateInputChange);
      
      if (!endDate) {
        const initialDate = new Date(sevenDaysBefore);
        initialDate.setDate(initialDate.getDate() - 1);
        endDateElement.valueAsDate = initialDate;
        setTimeout(() => {
          if (!endDate) {
            endDateElement.value = "";
          }
        }, 100);
      }
      
      return () => {
        endDateElement.removeEventListener('input', handleDateInputChange);
      };
    }
  }, [startDate, endDate]);
  
  const handleCloseErrorModal = () => {
    console.log("Error modal closed by user");
    
    document.querySelectorAll('div[style*="position: fixed"][style*="bottom"][style*="background-color: red"]')
      .forEach(el => el.remove());
    
    setErrorMessage('');
    setIsSubmitting(false);
  };
  
  // Form submission
  const handleSubmit = async () => {
    document.querySelectorAll('div[style*="position: fixed"][style*="bottom"][style*="right"][style*="background-color: red"]')
      .forEach(el => el.remove());
      
    if (files.length > 0 && startDate && endDate) {
      const startDateObj = new Date(startDate);
      startDateObj.setHours(0, 0, 0, 0); 
      
      const endDateObj = new Date(endDate);
      endDateObj.setHours(0, 0, 0, 0); 
      
      const sevenDaysBefore = new Date(startDateObj);
      sevenDaysBefore.setDate(startDateObj.getDate() - 7);
      sevenDaysBefore.setHours(0, 0, 0, 0); 
      
      if (endDateObj.getTime() >= sevenDaysBefore.getTime()) {
        alert("End date must be before " + formatDate(sevenDaysBefore) + " (7 days before start date)");
        return;
      }
      
      try {
        setIsSubmitting(true);
        setErrorMessage(''); 
        
        //initiate upload
        console.log("Starting upload process...");
        const { upload_url: uploadUrl, filename } = await initiateUpload(selectedFileName);
        console.log("Upload initiated with URL:", uploadUrl);
        
        //upload to S3
        try {
          console.log("Uploading to S3...");
          const s3Response = await uploadToS3(uploadUrl, files[0]);
          console.log("S3 upload response:", s3Response);
          
          // Check if S3 response indicates an error
          if (s3Response && s3Response.status === "error") {
            console.error("S3 error:", s3Response.message);
            setErrorMessage(s3Response.message || "Error during file upload");
            setIsSubmitting(false);
            return;
          }
          
        } catch (error) {
          // Handle S3 upload errors
          console.error("S3 upload error:", error);
          setErrorMessage(error.message || "File upload failed");
          setIsSubmitting(false);
          return;
        }
        
        await new Promise(resolve => setTimeout(resolve, 100));
        
        //analysis operation
        try {
          console.log("Starting analysis...");
          const analysisPayload = await analyze({
            filename,
            startDate,
            endDate,
            outputPrefix: 'forest_classification'
          });
          console.log("Analysis complete:", analysisPayload);
          
          // Check if analysis response indicates an error
          if (analysisPayload && analysisPayload.status === "error") {
            console.error("Analysis error:", analysisPayload.message);
            setErrorMessage(analysisPayload.message || "Error during analysis");
            setIsSubmitting(false);
            return;
          }
          
          
          sessionStorage.setItem('uploadComplete', 'true');
          sessionStorage.setItem('uploadData', JSON.stringify({
            fileName: selectedFileName,
            startDate,
            endDate
          }));
          
          // redirect with analysis results
          history.push('/landing', { 
            ...analysisPayload,
            startDate,
            endDate,
            selectedFile: files[0],
            uploadSuccess: true
          });
        } catch (error) {
          console.error("Analysis error:", error);
          setErrorMessage(error.message || "Analysis failed");
          setIsSubmitting(false);
        }
      } catch (error) {
        console.error('Upload process failed:', error);
        setErrorMessage(error.message || 'Upload failed');
        setIsSubmitting(false);
      }
    } else {
      if (!files.length) {
        alert('Please select a file before submitting');
      } else if (!startDate) {
        alert('Please select a start date before submitting');
      } else if (!endDate) {
        alert('Please select an end date before submitting');
      }
    }
  };

  const handleDateClick = (e) => {
    e.stopPropagation();
    if (files.length === 0) {
      e.preventDefault();
      alert('Please upload a file first before selecting dates');
    }
  };
     
  return (
    <div className="openearth-container">
      {/* Add style tag to hide error messages */}
      <style>
        {`
          div[style*="position: fixed"][style*="bottom"][style*="right"][style*="background-color: red"] {
            display: none !important;
            visibility: hidden !important;
            opacity: 0 !important;
          }
        `}
      </style>
      
      <main className="openearth-main">
        <div className={`earth-semicircle ${isRotating ? 'rotating' : ''}`}></div>
        <div className="drop-container">
          <div className="dropzone-card">
            {/* File upload area */}
            <div {...getRootProps()} className="file-upload-area" style={{ padding: '20px', textAlign: 'center' }}>
              <input {...getInputProps()} />
              <div className="upload-icon" style={{ display: 'flex', justifyContent: 'center', marginBottom: '15px' }}>
                <svg viewBox="0 0 80 80" width="80" height="80">
                  <path d="M45,30A15,15,0,0,0,15,20a10,10,0,0,0,0,20H45a8,8,0,0,0,0-16Z" fill="none" stroke="#000" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"/>
                  <line x1="32" y1="20" x2="32" y2="40" fill="none" stroke="#000" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"/>
                  <line x1="23" y1="28" x2="32" y2="20" fill="none" stroke="#000" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"/>
                  <line x1="41" y1="28" x2="32" y2="20" fill="none" stroke="#000" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"/>
                </svg>
              </div>
              <div className="dropzone-content" style={{ textAlign: 'center' }}>
                <p className="dropzone-text">
                  {isDragActive ? 'Drop files here' : 'Drag & drop files or'} <span className="browse-link">Browse</span>
                </p>
                <p className="supported-formats" style={{ fontSize: '14px'}}>Supported format : GEOJSON, JSON</p>
                {selectedFileName && (
                  <div className="text-sm text-green-600 mb-4" style={{ fontSize: '14px'}}>
                    <br></br>
                    <p>Selected file : <span style={{ fontWeight: 'bold', fontStyle: 'italic' }}>{selectedFileName}</span></p>
                  </div>
                )}
              </div>
            </div>

            {/* Date selection section */}
            <div 
              className="date-selection" 
              style={{ padding: '20px', paddingTop: '0' }}
              onMouseDown={(e) => {
                if (files.length === 0) {
                  e.preventDefault();
                  e.stopPropagation();
                  alert('Please upload a file first');
                  return false;
                }
              }}
              onClick={handleDateClick}
            >
              <div style={{ display: 'flex', alignItems: 'center', marginBottom: '15px', justifyContent: 'center' }}>
                <svg viewBox="0 0 24 24" width="20" height="20" style={{ marginRight: '8px' }}>
                  <rect x="3" y="4" width="18" height="18" rx="2" fill="none" stroke="currentColor" strokeWidth="2"/>
                  <line x1="3" y1="10" x2="21" y2="10" stroke="currentColor" strokeWidth="2"/>
                  <line x1="8" y1="2" x2="8" y2="6" stroke="currentColor" strokeWidth="2"/>
                  <line x1="16" y1="2" x2="16" y2="6" stroke="currentColor" strokeWidth="2"/>
                </svg>
                <label className="date-label" style={{ fontSize: '16px' }}>
                  Date Range:
                </label>
              </div>
              
              <div style={{ display: 'flex', gap: '10px' }}>
                {/* Start Date Picker */}
                <div style={{ flex: 1, textAlign: 'center' }}>
                  <input
                    type="date"
                    id="startDateInput"
                    value={startDate}
                    onChange={(e) => {
                      setStartDate(e.target.value);
                      setEndDate('');
                    }}
                    className="date-input"
                    style={{
                      width: '100%',
                      padding: '10px',
                      borderRadius: '4px',
                      border: '1px solid #ccc',
                      opacity: files.length > 0 ? '1' : '0.5',
                      pointerEvents: files.length > 0 ? 'auto' : 'none'
                    }}
                    onClick={handleDateClick}
                    onMouseDown={(e) => {
                      if (files.length === 0) {
                        e.preventDefault();
                        e.stopPropagation();
                        alert('Please upload a file first before selecting dates');
                        return false;
                      }
                    }}
                    disabled={files.length === 0}
                    max={todayFormatted}
                    onKeyDown={(e) => {
                      if (e.key === 'Tab') return;
                      const inputDate = new Date(e.target.value);
                      if (inputDate > today) {
                        e.preventDefault();
                      }
                    }}
                  />
                  <div className="text-xs text-gray-500 mt-1" style={{ textAlign: 'center', fontSize: '14px'}}>
                    Start
                  </div>
                </div>
                
                {/* End Date Picker */}
                <div style={{ flex: 1, textAlign: 'center' }}>
                  <input
                    type="date"
                    id="endDateInput"
                    ref={endDateInputRef}
                    value={endDate}
                    onChange={(e) => {
                      const selectedDate = new Date(e.target.value);
                      const startDateObj = new Date(startDate);
                      const sevenDaysBefore = new Date(startDateObj);
                      sevenDaysBefore.setDate(startDateObj.getDate() - 7);
                      
                      sevenDaysBefore.setHours(0, 0, 0, 0);
                      selectedDate.setHours(0, 0, 0, 0);
                      
                      if (selectedDate.getTime() < sevenDaysBefore.getTime()) {
                        setEndDate(e.target.value);
                      } else {
                        e.preventDefault();
                        e.target.value = endDate;
                        alert("Please select a date before " + formatDate(sevenDaysBefore) + " (7 days before start date)");
                      }
                    }}
                    className="date-input"
                    style={{
                      width: '100%',
                      padding: '10px',
                      borderRadius: '4px',
                      border: '1px solid #ccc',
                      opacity: (startDate && files.length > 0) ? '1' : '0.5',
                      pointerEvents: (startDate && files.length > 0) ? 'auto' : 'none'
                    }}
                    onClick={handleDateClick}
                    onMouseDown={(e) => {
                      if (files.length === 0) {
                        e.preventDefault();
                        e.stopPropagation();
                        alert('Please upload a file first before selecting dates');
                        return false;
                      }
                    }}
                    disabled={!startDate || files.length === 0}
                    max={startDate ? getOneWeekBefore(startDate) : todayFormatted}
                    onFocus={(e) => {
                      if (startDate) {
                        const startDateObj = new Date(startDate);
                        const eightDaysBefore = new Date(startDateObj);
                        eightDaysBefore.setDate(startDateObj.getDate() - 8);
                        e.target.max = formatDate(eightDaysBefore);
                      }
                    }}
                  />
                   <div className="text-xs text-gray-500 mt-1" style={{ textAlign: 'center', fontSize: '14px' }}>
                    End
                  </div>
                </div>
              </div>
            </div>
          </div>
          
          <button
            className="upload-button"
            onClick={handleSubmit}
            disabled={isSubmitting}
            style={{ opacity: isSubmitting ? 0.7 : 1, cursor: isSubmitting ? 'not-allowed' : 'pointer' }}>
            {isSubmitting ? 'PROCESSING...' : 'SUBMIT'}
          </button>
          
          {isSubmitting && !errorMessage && (
            <div style={{ textAlign: 'center', marginTop: '10px' }}>
              <div style={{
                width: '30px',
                height: '30px',
                border: '3px solid rgba(0, 0, 0, 0.1)',
                borderTop: '3px solid #020b18',
                borderRadius: '50%',
                animation: 'spin 1s linear infinite',
                margin: '0 auto'
              }}></div>
            </div>
          )}
        </div>
      </main>
      
      {/* Error Modal */}
      {/* Error Modal - render at the top level of the DOM */}
      {errorMessage && (
        <ErrorModal 
          message={errorMessage} 
          onClose={handleCloseErrorModal} 
        />
      )}
      
      <style>{`
        @keyframes spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
};

export default OpenEarthUpload;