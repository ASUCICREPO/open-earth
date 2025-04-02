import React from 'react'
import { useHistory } from 'react-router-dom'
// import './landing-page1.css'

const LandingPage1 = (props) => {
  const hist = useHistory();

  const handleBackClick = () => {
        hist.push('/');
  };
  
  return (
    <div className="landing-page1-container">
      
     Landing Page
    </div>
  )
}

export default LandingPage1
