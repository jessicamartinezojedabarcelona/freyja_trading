import { AbstractControl, ValidationErrors, ValidatorFn } from '@angular/forms';

/** Whether a field's error message should be shown: the control must be
 * invalid, and the user must have either already interacted with it
 * (blurred, i.e. touched) or attempted to submit the form — never before any
 * interaction at all. Keeping this in one place is what keeps the visible
 * message and the `aria-invalid` attribute in sync: both call this. */
export function shouldShowFieldError(control: AbstractControl, attemptedSubmit: boolean): boolean {
  return control.invalid && (control.touched || attemptedSubmit);
}

/** Cross-field validator for a "confirm password" control: compares its own
 * value against a sibling control in the same FormGroup, identified by name.
 * Attached directly to the confirm control (not the group) so its own
 * `invalid`/`touched` state — and therefore `shouldShowFieldError` above —
 * works exactly like every other field. The caller is responsible for
 * re-running this validator (`updateValueAndValidity()`) whenever the
 * sibling control's value changes, since Angular does not do that
 * automatically for a validator that reads outside its own control. */
export function passwordsMatchValidator(passwordControlName: string): ValidatorFn {
  return (control: AbstractControl): ValidationErrors | null => {
    const password = control.parent?.get(passwordControlName)?.value;
    if (password !== undefined && control.value !== password) {
      return { mismatch: true };
    }
    return null;
  };
}
