output "resource_group_name" {
  value       = azurerm_resource_group.rg.name
  description = "The name of the created Resource Group"
}

output "resource_group_id" {
  value       = azurerm_resource_group.rg.id
  description = "The resource ID of the created Resource Group"
}

output "acr_login_server" {
  value       = azurerm_container_registry.acr.login_server
  description = "The URL of the Container Registry"
}

output "acr_admin_username" {
  value       = azurerm_container_registry.acr.admin_username
  description = "The admin username for the registry"
}

output "acr_admin_password" {
  value       = azurerm_container_registry.acr.admin_password
  description = "The admin password for the registry"
  sensitive   = true
}

output "app_insights_connection_string" {
  value       = azurerm_application_insights.appinsights.connection_string
  description = "The connection string for Application Insights"
  sensitive   = true
}

output "api_url" {
  value       = "https://${azurerm_container_app.api.ingress[0].fqdn}"
  description = "The external URL of the API service"
}

output "frontend_url" {
  value       = "https://${azurerm_static_web_app.frontend.default_host_name}"
  description = "The default URL of the Static Web App frontend"
}
