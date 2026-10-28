package com.planirovanie.org;

import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.Optional;

public interface OrgStreamDocRepo extends JpaRepository<OrgStreamDoc, String> {

    /** Row-locks the stream document so concurrent PUTs serialize on it. */
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select d from OrgStreamDoc d where d.streamId = :id")
    Optional<OrgStreamDoc> findForUpdate(@Param("id") String id);
}
