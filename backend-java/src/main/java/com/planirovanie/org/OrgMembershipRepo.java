package com.planirovanie.org;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface OrgMembershipRepo extends JpaRepository<OrgMembership, Long> {
    List<OrgMembership> findByUsername(String username);
    List<OrgMembership> findByScopeTypeAndScopeId(String scopeType, String scopeId);
}
