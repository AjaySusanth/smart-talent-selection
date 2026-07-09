variable "project_name" {
  type        = string
  description = "The name of the project"
  default     = "talentforge"
}

variable "environment" {
  type        = string
  description = "The deployment environment (e.g. staging, production)"
  default     = "staging"
}

variable "location" {
  type        = string
  description = "The Azure region to deploy resources into"
  default     = "centralindia"
}

# Sensitive application secrets (Option B)
variable "api_key" {
  type      = string
  sensitive = true
}

variable "supabase_url" {
  type      = string
  sensitive = true
}

variable "supabase_service_key" {
  type      = string
  sensitive = true
}

variable "azure_di_endpoint" {
  type      = string
  sensitive = true
}

variable "azure_di_key" {
  type      = string
  sensitive = true
}

variable "gemini_api_key" {
  type      = string
  sensitive = true
}

variable "groq_api_key" {
  type      = string
  sensitive = true
}

variable "hf_api_token" {
  type      = string
  sensitive = true
}

variable "openai_api_key" {
  type      = string
  sensitive = true
}

variable "azure_openai_endpoint" {
  type      = string
  sensitive = true
}

variable "azure_openai_key" {
  type      = string
  sensitive = true
}

