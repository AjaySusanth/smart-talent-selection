resource "azurerm_container_registry" "acr" {
  # ACR name must be globally unique and alphanumeric only
  name                = "${var.project_name}${var.environment}acr"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  sku                 = "Basic"
  admin_enabled       = true

  tags = azurerm_resource_group.rg.tags
}
