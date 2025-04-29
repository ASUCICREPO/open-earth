import React, { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';

const MapAnalysis = () => {
  const [isLoading, setIsLoading] = useState(true);
  const location = useLocation();
  
  // pull results & image URL from router state
  const {
    analysis_results: jsonData = {},
    image_download_url: imageUrl = '',
    image_date: imageDate = '',
    startDate = '',
    endDate = ''
  } = location.state || {};
  
  const formatDate = (dateStr) => {
    if (!dateStr) return '';
    const [year, month, day] = dateStr.split('-');
    return `${month}-${day}-${year}`;
  };
  
  // Function to download JSON data
  const downloadJsonData = () => {
    const jsonString = JSON.stringify(jsonData, null, 2);
    const blob = new Blob([jsonString], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    let filename = 'forest-analysis';
    if (startDate && endDate) {
      filename += `-${startDate}-to-${endDate}`;
    }
    a.download = `${filename}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };
  
  // Function to download the map image
  const downloadMapImage = () => {
    const xhr = new XMLHttpRequest();
    xhr.open('GET', imageUrl, true);
    xhr.responseType = 'blob';
    
    xhr.onload = function() {
      if (this.status === 200) {
        const url = URL.createObjectURL(this.response);
        const a = document.createElement('a');
        a.href = url;
        let filename = 'forest-map';
        if (startDate && endDate) {
          filename += `-${startDate}-to-${endDate}`;
        }
        a.download = `${filename}.png`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }
    };
    
    xhr.send();
  };


  useEffect(() => {
    const timer = setTimeout(() => {
      setIsLoading(false);
    }, 6000); 
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    const originalStyle = document.body.style.cssText;
    document.body.style.background = 'linear-gradient(180deg, rgba(255, 255, 255, 1) 0%, rgba(186, 221, 240, 1) 90%)';
    document.body.style.margin = '0';
    document.body.style.padding = '0';
    document.body.style.minHeight = '100vh';
    document.body.style.width = '100%';
    return () => {
      document.body.style.cssText = originalStyle;
    };
  }, []);

  return (
    <div className="landing-page-container" style={{ 
      padding: 0,
      width: '100%',
      fontFamily: 'Arial, sans-serif',
      minHeight: 'calc(100vh - 100px)', 
    }}>
      <header style={{ 
        marginBottom: 0,
        padding: '20px'
      }}>
        <h1 style={{ 
          textAlign: 'center',
          fontFamily: 'Poppins, sans-serif',
          margin: 0
        }}>Map Analysis</h1>
        {startDate && endDate && (
          <div style={{ marginTop: '10px', textAlign: 'center' }}>
            <p style={{ fontFamily: 'Poppins, sans-serif', fontSize: '16px' }}>
              Date Range: {formatDate(startDate)} to {formatDate(endDate)}
            </p>
          </div>
        )}
      </header>

      <div style={{ padding: '30px 20px', maxWidth: '1500px', margin: '0 auto' }}>
        <div style={{ display: 'flex', gap: '30px', flexWrap: 'wrap', justifyContent: 'center' }}>
          {/* Map container */}
          <div style={{ 
            width: 'calc(30% - 15px)', 
            minWidth: '600px',
            backgroundColor: '#f5f5f5',
            borderRadius: '8px',
            overflow: 'hidden',
            boxShadow: '0 4px 8px rgba(0,0,0,0.1)'
          }}>
            <h2 style={{ 
              padding: '12px 20px', 
              backgroundColor: '#020b18', 
              margin: 0,
              borderBottom: '1px solid #ccc',
              fontFamily: 'Poppins, sans-serif',
              color: 'white',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center'
            }}>
              Map
              <svg 
                xmlns="http://www.w3.org/2000/svg" 
                width="20" 
                height="20" 
                viewBox="0 0 24 24" 
                fill="none" 
                stroke="white" 
                strokeWidth="2" 
                strokeLinecap="round" 
                strokeLinejoin="round" 
                style={{ cursor: 'pointer' }}
                onClick={downloadMapImage}
                title="Download Map"
              >
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
            </h2>
            <div style={{ 
              height: '700px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              position: 'relative'
            }}>
              {isLoading ? (
                <div className="loading-animation" style={{ textAlign: 'center' }}>
                  <div style={{
                    width: '50px',
                    height: '50px',
                    border: '5px solid #e0e0e0',
                    borderTop: '5px solid #3498db',
                    borderRadius: '50%',
                    animation: 'spin 1s linear infinite',
                    margin: '0 auto 15px'
                  }}></div>
                  <p>Loading map data...</p>
                </div>
              ) : (
                <div style={{ textAlign: 'center', width: '95%', height: '95%', overflow: 'hidden' }}>
                  <img 
                    src={imageUrl} 
                    alt={`Natural Forest Classification (${imageDate})`} 
                    style={{
                      width: '100%',
                      height: '100%',
                      objectFit: 'contain'
                    }}
                  />
                </div>
              )}
            </div>
          </div>

          {/* JSON container */}
          <div style={{ 
            width: 'calc(40% - 15px)', 
            minWidth: '350px',
            backgroundColor: '#f5f5f5',
            borderRadius: '8px',
            overflow: 'hidden',
            boxShadow: '0 4px 8px rgba(0,0,0,0.1)'
          }}>
            <h2 style={{ 
              padding: '12px 20px', 
              backgroundColor: '#020b18', 
              margin: 0,
              borderBottom: '1px solid #ccc',
              fontFamily: 'Poppins, sans-serif',
              color: 'white',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center'
            }}>  
              JSON
              <svg 
                xmlns="http://www.w3.org/2000/svg" 
                width="20" 
                height="20" 
                viewBox="0 0 24 24" 
                fill="none" 
                stroke="white" 
                strokeWidth="2" 
                strokeLinecap="round" 
                strokeLinejoin="round" 
                style={{ cursor: 'pointer' }}
                onClick={downloadJsonData}
                title="Download JSON"
              >
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
            </h2>
            <div style={{ height: '650px', position: 'relative' }}>
              {isLoading ? (
                <div className="loading-animation" style={{
                  textAlign: 'center',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  height: '100%'
                }}>
                  <div>
                    <div style={{
                      width: '50px',
                      height: '50px',
                      border: '5px solid #e0e0e0',
                      borderTop: '5px solid #3498db',
                      borderRadius: '50%',
                      animation: 'spin 1s linear infinite',
                      margin: '0 auto 15px'
                    }}></div>
                    <p>Parsing JSON data...</p>
                  </div>
                </div>
              ) : (
                <div style={{ 
                  padding: '20px',
                  fontFamily: 'monospace',
                  fontSize: '14px',
                  height: '100%',
                  overflowY: 'auto',
                  overflowX: 'hidden'
                }}>
                  <pre style={{ 
                    margin: 0,
                    whiteSpace: 'pre-wrap',
                    wordWrap: 'break-word'
                  }}>
                    {JSON.stringify(jsonData, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* CSS for loading animation */}
      <style>{`
        @keyframes spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
      `}</style>

      {/* Font import for Poppins */}
      <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600&display=swap" />
    </div>
  );
};

export default MapAnalysis;