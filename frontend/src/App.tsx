import { AuthProvider } from '@/contexts/AuthContext';
// import { BrowserRouter } from 'react-router-dom';  // Task 2.2

function App() {
  return (
    // <BrowserRouter>       {/* Task 2.2 */}
      <AuthProvider>
        {/* Your routes and layout will go here in Task 2.2 / 2.8 */}
        <div className="min-h-screen">
          <p>Auth framework loaded. Build login UI in Task 2.7.</p>
        </div>
      </AuthProvider>
    // </BrowserRouter>
  );
}

export default App;