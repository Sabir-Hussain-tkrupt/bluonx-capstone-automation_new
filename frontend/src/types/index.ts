// Type definitions for the BluOnX Capstone Automation system
// These will be populated as we build features

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: "admin" | "project_manager" | "viewer";
  avatar_url?: string;
  created_at: string;
}