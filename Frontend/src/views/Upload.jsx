import React, { useState, useCallback, useEffect } from 'react';
import { useDropzone } from 'react-dropzone';
import { useHistory } from 'react-router-dom';



const OpenEarthUpload = () => {
  const [files, setFiles] = useState([]);
  const [selectedFileName, setSelectedFileName] = useState('');
  const [isRotating, setIsRotating] = useState(true);
  
  const history = useHistory();
  
  useEffect(() => {
    setIsRotating(true);
  }, []);
  
  const onDrop = useCallback((acceptedFiles) => {
    setFiles(acceptedFiles);
    if (acceptedFiles.length > 0) {
      setSelectedFileName(acceptedFiles[0].name);
      console.log('Selected file:', acceptedFiles[0].name);
    }
  }, []);
  
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/json': ['.json', '.geojson']
    }
  });
    
  const handleUploadClick = () => {
    if (files.length > 0) {
        history.push('/date');
    } else {
      alert('Please select a file before uploading');
    }
  };
     
  return (
    <div className="openearth-container">
      
      <main className="openearth-main">
        <div className={`earth-semicircle ${isRotating ? 'rotating' : ''}`}></div>
        <div className="drop-container">
          <div className="dropzone-card" {...getRootProps()}>
            <input {...getInputProps()} />
            <div className="upload-icon">
              <svg viewBox="0 0 80 80" width="80" height="80">
                <path d="M45,30A15,15,0,0,0,15,20a10,10,0,0,0,0,20H45a8,8,0,0,0,0-16Z" fill="none" stroke="#000" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"/>
                <line x1="32" y1="20" x2="32" y2="40" fill="none" stroke="#000" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"/>
                <line x1="23" y1="28" x2="32" y2="20" fill="none" stroke="#000" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"/>
                <line x1="41" y1="28" x2="32" y2="20" fill="none" stroke="#000" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"/>
              </svg>
            </div>
            <div className="dropzone-content">
              <p className="dropzone-text">
                {isDragActive ? 'Drop files here' : 'Drag & drop files or'} <span className="browse-link">Browse</span>
              </p>
              <p className="supported-formats">Supported format : GEOJSON, JSON</p>
              {selectedFileName && (
                <div className="text-sm text-green-600 mb-4">
                  <br></br>
                  <p>Selected file: {selectedFileName}</p>
                </div>
              )}
            </div>
          </div>
          
          <button 
            className="upload-button"
            onClick={handleUploadClick}>
            UPLOAD
          </button>
        </div>
      </main>
    </div>
  );
};

export default OpenEarthUpload;