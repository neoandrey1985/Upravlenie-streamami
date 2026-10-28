package com.planirovanie.org;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface OrgStreamRepo extends JpaRepository<OrgStream, String> {
    List<OrgStream> findAllByOrderByOrdAsc();
}
