package com.planirovanie.org;

import org.hibernate.cfg.AvailableSettings;
import org.hibernate.context.spi.CurrentTenantIdentifierResolver;
import org.hibernate.engine.jdbc.connections.spi.MultiTenantConnectionProvider;
import org.springframework.boot.autoconfigure.orm.jpa.HibernatePropertiesCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.SQLException;

/**
 * Schema-per-team multi-tenancy (Hibernate SCHEMA strategy). Every JPA session opens a connection
 * switched to the current team's schema ({@link TenantContext}); the team-level entities, repositories
 * and StateService stay exactly as in the base project — that keeps upstream merges conflict-free.
 */
@Configuration
public class SchemaTenancyConfig {

    @Bean
    public SchemaConnectionProvider schemaConnectionProvider(DataSource ds) {
        return new SchemaConnectionProvider(ds);
    }

    @Bean
    public HibernatePropertiesCustomizer tenancyCustomizer(SchemaConnectionProvider provider) {
        CurrentTenantIdentifierResolver<String> resolver = new CurrentTenantIdentifierResolver<>() {
            @Override public String resolveCurrentTenantIdentifier() { return TenantContext.get(); }
            @Override public boolean validateExistingCurrentSessions() { return true; }
        };
        return props -> {
            props.put(AvailableSettings.MULTI_TENANT_CONNECTION_PROVIDER, provider);
            props.put(AvailableSettings.MULTI_TENANT_IDENTIFIER_RESOLVER, resolver);
        };
    }

    /** Hands out pooled connections switched to the tenant's schema and resets them on release. */
    public static class SchemaConnectionProvider implements MultiTenantConnectionProvider<String> {
        private final DataSource ds;
        private volatile String defaultSchema;

        SchemaConnectionProvider(DataSource ds) { this.ds = ds; }

        /** The connection's default schema ("public" on PostgreSQL, "PUBLIC" on H2). */
        public String defaultSchema() {
            if (defaultSchema == null) {
                try (Connection c = ds.getConnection()) { defaultSchema = c.getSchema(); }
                catch (SQLException e) { throw new IllegalStateException("cannot read default schema", e); }
            }
            return defaultSchema;
        }

        @Override public Connection getAnyConnection() throws SQLException { return ds.getConnection(); }
        @Override public void releaseAnyConnection(Connection c) throws SQLException { c.close(); }

        @Override
        public Connection getConnection(String tenant) throws SQLException {
            Connection c = getAnyConnection();
            try {
                c.setSchema(TenantContext.DEFAULT.equals(tenant) ? defaultSchema() : tenant);
            } catch (SQLException e) { c.close(); throw e; }
            return c;
        }

        @Override
        public void releaseConnection(String tenant, Connection c) throws SQLException {
            try { c.setSchema(defaultSchema()); } finally { c.close(); }   // pooled: never leak a team schema
        }

        @Override public boolean supportsAggressiveRelease() { return false; }
        @Override public boolean isUnwrappableAs(Class<?> t) { return false; }
        @Override public <T> T unwrap(Class<T> t) { throw new UnsupportedOperationException(); }
    }
}
