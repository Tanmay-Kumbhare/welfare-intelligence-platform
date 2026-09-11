import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, SlidersHorizontal } from "lucide-react";
import Button from "../components/ui/Button";
import Card from "../components/ui/Card";
import Badge from "../components/ui/Badge";
import Input from "../components/ui/Input";
import Select from "../components/ui/Select";
import SectionHeader from "../components/ui/SectionHeader";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/StatusStates";
import { schemeService } from "../services/api";
import {
  DISCOVERY_FILTERS,
  matchesDiscoveryFilter,
} from "../utils/schemeInsights";
import { categoryLabel } from "../utils/ruleFormat";

export default function SchemesPage() {
  const [schemes, setSchemes] = useState([]);
  const [details, setDetails] = useState(new Map());
  const [status, setStatus] = useState("loading");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [discovery, setDiscovery] = useState("");
  const [sort, setSort] = useState("name");

  const loadSchemes = () => {
    Promise.resolve(schemeService.getAll())
      .then(async (response) => {
        const list = Array.isArray(response.data) ? response.data : [];
        const detailResponses = await Promise.all(
          list.map((scheme) => schemeService.get(scheme.scheme_id))
        );
        const detailMap = new Map(
          detailResponses.map((responseItem) => [responseItem.data.scheme_id, responseItem.data])
        );
        setSchemes(list);
        setDetails(detailMap);
        setStatus("ready");
      })
      .catch(() => setStatus("error"));
  };

  useEffect(() => {
    loadSchemes();
  }, []);

  const categories = useMemo(
    () => [...new Set(schemes.map((scheme) => scheme.scheme_category).filter(Boolean))].sort(),
    [schemes]
  );

  const filteredSchemes = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    const result = schemes.filter((scheme) => {
      const matchesQuery = !normalizedQuery || scheme.scheme_name.toLowerCase().includes(normalizedQuery);
      const matchesCategory = !category || scheme.scheme_category === category;
      const matchesDiscovery = !discovery || matchesDiscoveryFilter(
        scheme,
        details.get(scheme.scheme_id),
        discovery
      );
      return matchesQuery && matchesCategory && matchesDiscovery;
    });

    return result.sort((first, second) => {
      if (sort === "category") {
        return (first.scheme_category || "").localeCompare(second.scheme_category || "") ||
          first.scheme_name.localeCompare(second.scheme_name);
      }
      if (sort === "verified") {
        return (second.last_verified_at || "").localeCompare(first.last_verified_at || "") ||
          first.scheme_name.localeCompare(second.scheme_name);
      }
      return first.scheme_name.localeCompare(second.scheme_name);
    });
  }, [category, details, discovery, query, schemes, sort]);

  const clearFilters = () => {
    setQuery("");
    setCategory("");
    setDiscovery("");
    setSort("name");
  };

  if (status === "loading") return <LoadingState label="Loading schemes..." />;
  if (status === "error") {
    return (
      <ErrorState
        title="Unable to load schemes"
        message="Unable to load schemes. Please try again."
        onRetry={() => {
          setStatus("loading");
          loadSchemes();
        }}
      />
    );
  }

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-[30px] mb-3">Explore schemes</h1>
        <p className="max-w-[68ch] mb-0">
          Search the active welfare scheme catalogue and inspect the rules, documents, and official links recorded for each scheme.
        </p>
      </div>

      <section aria-label="Scheme filters" className="border-y border-line py-5 mb-9">
        <div className="flex items-center gap-2 mb-4">
          <SlidersHorizontal className="h-4 w-4 text-accent-ink" aria-hidden="true" />
          <h2 className="text-lg mb-0">Filter schemes</h2>
        </div>
        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-x-4">
          <Input
            id="scheme-search"
            label="Search by name"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search schemes"
            type="search"
          />
          <Select
            id="scheme-category"
            label="Category"
            value={category}
            onChange={(event) => setCategory(event.target.value)}
          >
            <option value="">All categories</option>
            {categories.map((value) => <option key={value} value={value}>{categoryLabel(value)}</option>)}
          </Select>
          <Select
            id="scheme-discovery"
            label="Relevant factor"
            value={discovery}
            onChange={(event) => setDiscovery(event.target.value)}
          >
            <option value="">All citizen groups</option>
            {DISCOVERY_FILTERS.map((filter) => (
              <option key={filter.value} value={filter.value}>{filter.label}</option>
            ))}
          </Select>
          <Select id="scheme-sort" label="Sort by" value={sort} onChange={(event) => setSort(event.target.value)}>
            <option value="name">Name A-Z</option>
            <option value="category">Category</option>
            <option value="verified">Last verified</option>
          </Select>
        </div>
        <Button variant="ghost" size="sm" onClick={clearFilters} className="px-0">
          Clear filters
        </Button>
      </section>

      <SectionHeader title="Scheme catalogue" count={filteredSchemes.length} />
      {filteredSchemes.length === 0 ? (
        <EmptyState
          title="No schemes match your current filters."
          message="Try a different search or clear one of the filters."
          action={<Button variant="secondary" size="sm" onClick={clearFilters}>Clear filters</Button>}
        />
      ) : (
        <div className="grid md:grid-cols-2 gap-4">
          {filteredSchemes.map((scheme) => (
            <Card key={scheme.scheme_id} className="flex flex-col">
              <div className="flex items-start justify-between gap-3 mb-3">
                <Badge variant="neutral">{categoryLabel(scheme.scheme_category)}</Badge>
                <Badge variant={scheme.status === "ACTIVE" ? "ok" : "excl"}>
                  {scheme.status}
                </Badge>
              </div>
              <h2 className="text-xl mb-1">
                <Link to={`/schemes/${scheme.scheme_id}`} className="hover:text-accent-ink">
                  {scheme.scheme_name}
                </Link>
              </h2>
              {scheme.department_name && <p className="text-xs mb-3">{scheme.department_name}</p>}
              {scheme.benefit_description && <p className="text-sm mb-2">{scheme.benefit_description}</p>}
              {scheme.description && <p className="text-sm mb-4">{scheme.description}</p>}
              <div className="mt-auto flex flex-wrap items-center gap-3 pt-3 border-t border-line">
                <Link to={`/schemes/${scheme.scheme_id}`} className="text-sm font-medium">View details</Link>
                {scheme.official_source_url && (
                  <a href={scheme.official_source_url} target="_blank" rel="noreferrer" className="text-xs inline-flex items-center gap-1">
                    Official source <ArrowUpRight className="h-3 w-3" aria-hidden="true" />
                  </a>
                )}
                {scheme.application_url && <span className="text-xs text-ok-ink">Application available</span>}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
