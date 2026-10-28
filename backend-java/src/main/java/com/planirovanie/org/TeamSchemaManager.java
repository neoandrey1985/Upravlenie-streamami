package com.planirovanie.org;

import org.flywaydb.core.Flyway;
import org.springframework.boot.autoconfigure.flyway.FlywayMigrationStrategy;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

import javax.sql.DataSource;
import java.sql.Connection;
import java.util.List;
import java.util.regex.Pattern;

/**
 * Creates, migrates and drops the per-team schemas.
 *  - PostgreSQL (production): every team schema is migrated with the base project's db/migration
 *    (Flyway, own history table inside the schema); platform tables use db/platform in public.
 *  - H2 (tests, Flyway disabled, tables built by Hibernate): a new schema gets a DDL copy of the
 *    default schema's tables (SCRIPT NODATA), so tests exercise the same tenancy without PostgreSQL.
 */
@Configuration
public class TeamSchemaManager {
    private static final Pattern SAFE = Pattern.compile("[A-Za-z][A-Za-z0-9_]{0,62}");
    private final DataSource ds;
    private final SchemaTenancyConfig.SchemaConnectionProvider provider;
    private final JdbcTemplate jdbc;
    private volatile Boolean h2;

    public TeamSchemaManager(DataSource ds, SchemaTenancyConfig.SchemaConnectionProvider provider) {
        this.ds = ds; this.provider = provider; this.jdbc = new JdbcTemplate(ds);
    }

    /** Spring Boot runs this instead of the plain migrate(): team schema (public), then platform, then all team schemas. */
    @Bean
    public FlywayMigrationStrategy teamAwareMigration() {
        return flyway -> { flyway.migrate(); migratePlatform(); migrateAllTeams(); };
    }

    public boolean isH2() {
        if (h2 == null) {
            try (Connection c = ds.getConnection()) { h2 = c.getMetaData().getDatabaseProductName().toUpperCase().contains("H2"); }
            catch (Exception e) { h2 = false; }
        }
        return h2;
    }

    /** Physical schema name for a team id (H2 folds unquoted identifiers to upper case). */
    public String schemaFor(String teamId) {
        String s = "team_" + teamId;
        return isH2() ? s.toUpperCase() : s;
    }

    public void migratePlatform() {
        Flyway.configure().dataSource(ds).locations("classpath:db/platform").table("platform_schema_history")
              .baselineOnMigrate(true).baselineVersion("0").load().migrate();
    }

    public void migrateAllTeams() {
        List<String> schemas = jdbc.queryForList("SELECT schema_name FROM org_teams WHERE schema_name IS NOT NULL", String.class);
        for (String s : schemas) teamFlyway(s).migrate();
    }

    public void provision(String schema) {
        check(schema);
        if (isH2()) cloneDefaultSchemaH2(schema);
        else teamFlyway(schema).migrate();
    }

    public void drop(String schema) {
        check(schema);
        if (schema.equalsIgnoreCase(provider.defaultSchema())) throw new IllegalArgumentException("default schema cannot be dropped");
        jdbc.execute("DROP SCHEMA IF EXISTS \"" + schema + "\" CASCADE");
    }

    private Flyway teamFlyway(String schema) {
        return Flyway.configure().dataSource(ds).schemas(schema).locations("classpath:db/migration").load();
    }

    private void cloneDefaultSchemaH2(String schema) {
        String src = provider.defaultSchema();
        jdbc.execute("CREATE SCHEMA IF NOT EXISTS \"" + schema + "\"");
        List<String> script = jdbc.queryForList("SCRIPT NODATA NOPASSWORDS NOSETTINGS SCHEMA \"" + src + "\"", String.class);
        for (String st : script) {
            String u = st.trim();
            boolean ddl = u.startsWith("CREATE MEMORY TABLE") || u.startsWith("CREATE CACHED TABLE") || u.startsWith("CREATE TABLE")
                    || u.startsWith("ALTER TABLE") || u.startsWith("CREATE SEQUENCE") || u.startsWith("CREATE INDEX")
                    || u.startsWith("CREATE UNIQUE INDEX");
            if (ddl) jdbc.execute(u.replace("\"" + src + "\".", "\"" + schema + "\"."));
        }
    }

    private static void check(String schema) {
        if (schema == null || !SAFE.matcher(schema).matches()) throw new IllegalArgumentException("bad schema name: " + schema);
    }
}
