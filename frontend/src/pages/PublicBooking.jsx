import { useParams } from "react-router-dom";
import BookingForm from "../components/BookingForm";

export default function OwnerBook() {
  const { id } = useParams();
  return <BookingForm key={id || "shop"} variant="owner" shopId={id} />;
}
