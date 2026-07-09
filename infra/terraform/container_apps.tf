resource "azurerm_container_app_environment" "env" {
  name                       = "${var.project_name}-${var.environment}-env"
  location                   = azurerm_resource_group.rg.location
  resource_group_name        = azurerm_resource_group.rg.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.law.id

  tags = azurerm_resource_group.rg.tags
}

# Managed Identity used by the Container Apps to pull images and read Key Vault
resource "azurerm_user_assigned_identity" "aca_identity" {
  name                = "${var.project_name}-${var.environment}-aca-id"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
}

# Grant ACR Pull permissions to the Managed Identity
resource "azurerm_role_assignment" "aca_acr_pull" {
  scope                = azurerm_container_registry.acr.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.aca_identity.principal_id
}

# API App
resource "azurerm_container_app" "api" {
  name                         = "${var.project_name}-${var.environment}-api"
  container_app_environment_id = azurerm_container_app_environment.env.id
  resource_group_name          = azurerm_resource_group.rg.name
  revision_mode                = "Single"

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.aca_identity.id]
  }

  registry {
    server   = azurerm_container_registry.acr.login_server
    identity = azurerm_user_assigned_identity.aca_identity.id
  }

  secret {
    name                = "database-url"
    key_vault_secret_id = azurerm_key_vault_secret.db_url.id
    identity            = azurerm_user_assigned_identity.aca_identity.id
  }

  secret {
    name                = "redis-url"
    key_vault_secret_id = azurerm_key_vault_secret.redis_url.id
    identity            = azurerm_user_assigned_identity.aca_identity.id
  }

  secret {
    name                = "api-key"
    key_vault_secret_id = azurerm_key_vault_secret.api_key.id
    identity            = azurerm_user_assigned_identity.aca_identity.id
  }

  secret {
    name                = "supabase-url"
    key_vault_secret_id = azurerm_key_vault_secret.supabase_url.id
    identity            = azurerm_user_assigned_identity.aca_identity.id
  }

  secret {
    name                = "supabase-service-key"
    key_vault_secret_id = azurerm_key_vault_secret.supabase_service_key.id
    identity            = azurerm_user_assigned_identity.aca_identity.id
  }

  secret {
    name                = "azure-di-endpoint"
    key_vault_secret_id = azurerm_key_vault_secret.azure_di_endpoint.id
    identity            = azurerm_user_assigned_identity.aca_identity.id
  }

  secret {
    name                = "azure-di-key"
    key_vault_secret_id = azurerm_key_vault_secret.azure_di_key.id
    identity            = azurerm_user_assigned_identity.aca_identity.id
  }

  secret {
    name                = "gemini-api-key"
    key_vault_secret_id = azurerm_key_vault_secret.gemini_api_key.id
    identity            = azurerm_user_assigned_identity.aca_identity.id
  }

  secret {
    name                = "groq-api-key"
    key_vault_secret_id = azurerm_key_vault_secret.groq_api_key.id
    identity            = azurerm_user_assigned_identity.aca_identity.id
  }

  secret {
    name                = "hf-api-token"
    key_vault_secret_id = azurerm_key_vault_secret.hf_api_token.id
    identity            = azurerm_user_assigned_identity.aca_identity.id
  }

  secret {
    name                = "openai-api-key"
    key_vault_secret_id = azurerm_key_vault_secret.openai_api_key.id
    identity            = azurerm_user_assigned_identity.aca_identity.id
  }

  secret {
    name                = "azure-openai-endpoint"
    key_vault_secret_id = azurerm_key_vault_secret.azure_openai_endpoint.id
    identity            = azurerm_user_assigned_identity.aca_identity.id
  }

  secret {
    name                = "azure-openai-key"
    key_vault_secret_id = azurerm_key_vault_secret.azure_openai_key.id
    identity            = azurerm_user_assigned_identity.aca_identity.id
  }

  template {
    min_replicas = 1
    max_replicas = 2
    container {
      name    = "api"
      image   = "${azurerm_container_registry.acr.login_server}/backend:latest"
      cpu     = 0.5
      memory  = "1Gi"
      command = ["uvicorn"]
      args    = ["app.main:app", "--host", "0.0.0.0", "--port", "8000"]
      
      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }

      env {
        name  = "VERSION"
        value = "1.0.2" # Bumping this forces a new revision to pull the pushed image
      }

      env {
        name  = "LOG_LEVEL"
        value = "INFO"
      }

      env {
        name        = "DATABASE_URL"
        secret_name = "database-url"
      }

      env {
        name        = "REDIS_URL"
        secret_name = "redis-url"
      }

      env {
        name        = "API_KEY"
        secret_name = "api-key"
      }

      env {
        name        = "SUPABASE_URL"
        secret_name = "supabase-url"
      }

      env {
        name        = "SUPABASE_SERVICE_KEY"
        secret_name = "supabase-service-key"
      }

      env {
        name        = "AZURE_DI_ENDPOINT"
        secret_name = "azure-di-endpoint"
      }

      env {
        name        = "AZURE_DI_KEY"
        secret_name = "azure-di-key"
      }

      env {
        name        = "GEMINI_API_KEY"
        secret_name = "gemini-api-key"
      }

      env {
        name        = "GROQ_API_KEY"
        secret_name = "groq-api-key"
      }

      env {
        name        = "HF_API_TOKEN"
        secret_name = "hf-api-token"
      }

      env {
        name        = "OPENAI_API_KEY"
        secret_name = "openai-api-key"
      }

      env {
        name        = "AZURE_OPENAI_ENDPOINT"
        secret_name = "azure-openai-endpoint"
      }

      env {
        name        = "AZURE_OPENAI_KEY"
        secret_name = "azure-openai-key"
      }
    }
  }

  ingress {
    allow_insecure_connections = false
    external_enabled           = true
    target_port                = 8000
    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }

  tags = azurerm_resource_group.rg.tags
}

# Worker App
resource "azurerm_container_app" "worker" {
  name                         = "${var.project_name}-${var.environment}-worker"
  container_app_environment_id = azurerm_container_app_environment.env.id
  resource_group_name          = azurerm_resource_group.rg.name
  revision_mode                = "Single"

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.aca_identity.id]
  }

  registry {
    server   = azurerm_container_registry.acr.login_server
    identity = azurerm_user_assigned_identity.aca_identity.id
  }

  secret {
    name                = "database-url"
    key_vault_secret_id = azurerm_key_vault_secret.db_url.id
    identity            = azurerm_user_assigned_identity.aca_identity.id
  }

  secret {
    name                = "redis-url"
    key_vault_secret_id = azurerm_key_vault_secret.redis_url.id
    identity            = azurerm_user_assigned_identity.aca_identity.id
  }

  secret {
    name                = "api-key"
    key_vault_secret_id = azurerm_key_vault_secret.api_key.id
    identity            = azurerm_user_assigned_identity.aca_identity.id
  }

  secret {
    name                = "supabase-url"
    key_vault_secret_id = azurerm_key_vault_secret.supabase_url.id
    identity            = azurerm_user_assigned_identity.aca_identity.id
  }

  secret {
    name                = "supabase-service-key"
    key_vault_secret_id = azurerm_key_vault_secret.supabase_service_key.id
    identity            = azurerm_user_assigned_identity.aca_identity.id
  }

  secret {
    name                = "azure-di-endpoint"
    key_vault_secret_id = azurerm_key_vault_secret.azure_di_endpoint.id
    identity            = azurerm_user_assigned_identity.aca_identity.id
  }

  secret {
    name                = "azure-di-key"
    key_vault_secret_id = azurerm_key_vault_secret.azure_di_key.id
    identity            = azurerm_user_assigned_identity.aca_identity.id
  }

  secret {
    name                = "gemini-api-key"
    key_vault_secret_id = azurerm_key_vault_secret.gemini_api_key.id
    identity            = azurerm_user_assigned_identity.aca_identity.id
  }

  secret {
    name                = "groq-api-key"
    key_vault_secret_id = azurerm_key_vault_secret.groq_api_key.id
    identity            = azurerm_user_assigned_identity.aca_identity.id
  }

  secret {
    name                = "hf-api-token"
    key_vault_secret_id = azurerm_key_vault_secret.hf_api_token.id
    identity            = azurerm_user_assigned_identity.aca_identity.id
  }

  secret {
    name                = "openai-api-key"
    key_vault_secret_id = azurerm_key_vault_secret.openai_api_key.id
    identity            = azurerm_user_assigned_identity.aca_identity.id
  }

  secret {
    name                = "azure-openai-endpoint"
    key_vault_secret_id = azurerm_key_vault_secret.azure_openai_endpoint.id
    identity            = azurerm_user_assigned_identity.aca_identity.id
  }

  secret {
    name                = "azure-openai-key"
    key_vault_secret_id = azurerm_key_vault_secret.azure_openai_key.id
    identity            = azurerm_user_assigned_identity.aca_identity.id
  }

  template {
    min_replicas = 1
    max_replicas = 2
    container {
      name    = "worker"
      image   = "${azurerm_container_registry.acr.login_server}/backend:latest"
      cpu     = 0.5
      memory  = "1Gi"
      command = ["celery"]
      args    = ["-A", "app.workers.celery_app", "worker", "--loglevel=info"]
      
      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }

      env {
        name  = "VERSION"
        value = "1.0.2" # Forces a new revision
      }

      env {
        name  = "LOG_LEVEL"
        value = "INFO"
      }

      env {
        name        = "DATABASE_URL"
        secret_name = "database-url"
      }

      env {
        name        = "REDIS_URL"
        secret_name = "redis-url"
      }

      env {
        name        = "API_KEY"
        secret_name = "api-key"
      }

      env {
        name        = "SUPABASE_URL"
        secret_name = "supabase-url"
      }

      env {
        name        = "SUPABASE_SERVICE_KEY"
        secret_name = "supabase-service-key"
      }

      env {
        name        = "AZURE_DI_ENDPOINT"
        secret_name = "azure-di-endpoint"
      }

      env {
        name        = "AZURE_DI_KEY"
        secret_name = "azure-di-key"
      }

      env {
        name        = "GEMINI_API_KEY"
        secret_name = "gemini-api-key"
      }

      env {
        name        = "GROQ_API_KEY"
        secret_name = "groq-api-key"
      }

      env {
        name        = "HF_API_TOKEN"
        secret_name = "hf-api-token"
      }

      env {
        name        = "OPENAI_API_KEY"
        secret_name = "openai-api-key"
      }

      env {
        name        = "AZURE_OPENAI_ENDPOINT"
        secret_name = "azure-openai-endpoint"
      }

      env {
        name        = "AZURE_OPENAI_KEY"
        secret_name = "azure-openai-key"
      }
    }
  }

  tags = azurerm_resource_group.rg.tags
}
