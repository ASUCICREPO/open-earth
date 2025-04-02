import React, { useState,useEffect } from 'react';
import DatePicker from 'react-datepicker';
import { useHistory } from 'react-router-dom'; 
import 'react-datepicker/dist/react-datepicker.css';
import './OpenEarthDatePicker.css';

const OpenEarthDatePicker = () => {
  const [selectedDate, setSelectedDate] = useState(null);
  const [isDatePickerOpen, setIsDatePickerOpen] = useState(false);
  const [isRotating, setIsRotating] = useState(false);
  
  useEffect(() => {
      setIsRotating(true);
    }, []);
    
  const handleDateChange = (date) => {
    // Add date validation here
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    
    if (date <= today) {
      setSelectedDate(date);
      setIsDatePickerOpen(false);
    }
  };
  
  const formatDate = (date) => {
    if (!date) return 'mm/dd/yyyy';
    
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const year = date.getFullYear();
    
    return `${month}/${day}/${year}`;
  };
  
  const hist = useHistory();

  const handleOkClick = () => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    
    if (selectedDate && selectedDate <= today) {
      setTimeout(() => {
        hist.push('/landing');
      }, 3000);
    } else {
      alert('Please select a valid date (today or in the past)');
    }
  };
  
  return (
    <div className="openearth-container">
      
      
      <main className="openearth-main">
        <div className={`earth-circle ${isRotating ? 'rotating' : ''}`}></div>
        <div className="date-picker-container">
          <div className="date-picker-card">
            <div className="upload-icon">
              <svg viewBox="0 0 64 64" width="64" height="64">
                <path d="M45,30A15,15,0,0,0,15,20a10,10,0,0,0,0,20H45a8,8,0,0,0,0-16Z" fill="none" stroke="#000" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"/>
                <line x1="32" y1="20" x2="32" y2="40" fill="none" stroke="#000" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"/>
                <line x1="23" y1="28" x2="32" y2="20" fill="none" stroke="#000" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"/>
                <line x1="41" y1="28" x2="32" y2="20" fill="none" stroke="#000" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"/>
              </svg>
            </div>
            <p className="date-instruction">Please provide date for accurate information</p>
            
            <div className="date-input-wrapper">
              <input
                type="text"
                className="date-input"
                value={formatDate(selectedDate)}
                onClick={() => setIsDatePickerOpen(!isDatePickerOpen)}
                readOnly
              />
              {isDatePickerOpen && (
                <div className="date-picker-dropdown">
              {/* <input
                type="date"
                onChange={handleDateChange}
                value={selectedDate}
                dateFormat="MM/dd/yyyy"
                    maxDate={new Date()} // Prevent selecting future dates
              /> */}
                  <DatePicker
                    selected={selectedDate}
                    onChange={handleDateChange}
                    inline
                    dateFormat="MM/dd/yyyy"
                    maxDate={new Date()} // Prevent selecting future dates
                  />
                </div>
              )}
            </div>
            
            <button
              className="ok-button"
              onClick={handleOkClick}
              disabled={!selectedDate}
            >
              OK
            </button>
          </div>
        </div>
      </main>
    </div>
  );
};

export default OpenEarthDatePicker;
