import React, { useEffect } from 'react';

const ErrorModal = ({ message, onClose }) => {
  useEffect(() => {
    console.log("ErrorModal mounted with message:", message);
    
    return () => {
      console.log("ErrorModal unmounted");
    };
  }, [message, onClose]);

  return (
    <div 
      className="error-modal-overlay" 
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.7)',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        zIndex: 9999
      }}
    >
      <div 
        className="error-modal" 
        style={{
          backgroundColor: 'white',
          padding: '25px',
          borderRadius: '8px',
          boxShadow: '0 4px 20px rgba(0, 0, 0, 0.2)',
          width: '90%',
          maxWidth: '450px',
          textAlign: 'center',
          position: 'relative',
          animation: 'fadeIn 0.3s ease-out'
        }}
      >
        <h3 style={{ 
          margin: '0 0 20px 0', 
          color: '#d32f2f',
          fontSize: '20px'
        }}>
          Error
        </h3>
        <p style={{ 
          marginBottom: '25px', 
          fontSize: '16px',
          lineHeight: '1.5',
          color: '#333'
        }}>
          {message}
        </p>
        <button 
          onClick={onClose}
          style={{
            padding: '10px 30px',
            backgroundColor: '#020b18',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: 'pointer',
            fontSize: '16px',
            fontWeight: 'bold',
            transition: 'background-color 0.2s'
          }}
          onMouseOver={(e) => e.target.style.backgroundColor = '#0a3b66'}
          onMouseOut={(e) => e.target.style.backgroundColor = '#020b18'}
        >
          OK
        </button>
      </div>
      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(-20px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
};

export default ErrorModal;