resource "azurerm_managed_redis" "redis" {
  name                = "${var.project_name}-${var.environment}-redis"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  sku_name            = "Balanced_B0"

  default_database {
    access_keys_authentication_enabled = true
  }

  tags = azurerm_resource_group.rg.tags
}
