import React from 'react';
import { Route, Redirect } from 'react-router-dom';

const ProtectedRoute = ({ component: Component, ...rest }) => {
  const hasStateData = rest.location.state && rest.location.state.selectedFile;
  const hasSessionData = sessionStorage.getItem('uploadComplete') === 'true';
  const hasUploaded = hasStateData || hasSessionData;
  
  return (
    <Route
      {...rest}
      render={props =>
        hasUploaded ? (
          <Component {...props} />
        ) : (
          <Redirect
            to={{
              pathname: "/",
              state: { from: props.location, error: "Please upload a file first" }
            }}
          />
        )
      }
    />
  );
};

export default ProtectedRoute;