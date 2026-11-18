import { Link } from "react-router-dom";
import { getPortalAuth } from "../lib/portalApi";

export function bookJobPath() {
  return getPortalAuth() ? "/portal/book" : "/signup";
}

export default function BookJobLink({ className, children, onClick }) {
  return (
    <Link className={className} to={bookJobPath()} onClick={onClick}>
      {children}
    </Link>
  );
}
