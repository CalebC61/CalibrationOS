import "@testing-library/jest-dom";

process.env.REACT_APP_STRIPE_PUBLISHABLE_KEY = process.env.REACT_APP_STRIPE_PUBLISHABLE_KEY || "pk_test_123";
process.env.REACT_APP_BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "http://localhost:8001";
delete process.env.REACT_APP_GOOGLE_MAPS_API_KEY;
